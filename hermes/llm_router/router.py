import time
import uuid
import json
import asyncio
import logging
import traceback
import hashlib
import threading
import os
import atexit

from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from collections import defaultdict, deque

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator

from llm_gateway import (
    execute_protected,
    submit_task,
    metrics as gateway_metrics,
    health_status as gateway_health_status,
    CONFIG as GATEWAY_CONFIG,
    GatewayError,
    NoProvidersAvailableError,
)

# =========================================
# 🚀 APP INIT
# =========================================

app = FastAPI(title="Hermes Router PRO", version="6.0", docs_url="/docs", redoc_url=None)

# =========================================
# ⚙️ CONFIG CENTRAL
# =========================================

class Settings:
    MAX_MESSAGES = 20
    MAX_CONTENT_LENGTH = 20000

    REQUEST_TIMEOUT = 60
    MAX_STRATEGY_RETRIES = 3

    FAILURE_THRESHOLD = 5
    RECOVERY_TIME = 30

    CACHE_TTL = 300
    MAX_CACHE_SIZE = 1000

    ENABLE_LEARNING = True

    # Sem Field(ge=.., le=..) no Pydantic — ver ChatRequest abaixo.
    # Constraints do Pydantic rodam ANTES de qualquer handler custom e
    # geram 422 "cru", que o Hermes trata como erro fatal não-retryable.
    MAX_TOKENS_HARD_CAP = 8192
    MAX_TOKENS_FLOOR = 16
    DEFAULT_MAX_TOKENS = 1024

    TEMPERATURE_MIN = 0.0
    TEMPERATURE_MAX = 2.0

    # NOVO: orçamento de caracteres do contexto ANTES de mandar pro
    # provider (aprox. 4 chars/token). Alinhado com o `context.max_tokens`
    # do config do Hermes (120000 tokens ~ 480000 chars), mas com teto
    # bem mais conservador pra latência/custo real de request único.
    CONTEXT_CHAR_BUDGET = int(os.getenv("ROUTER_CONTEXT_CHAR_BUDGET", "16000"))

    # NOVO: nunca devolve 5xx pro cliente por esgotamento de estratégias —
    # devolve 200 com uma resposta de degradação clara. Desliga só se você
    # PRECISAR que o cliente veja o erro de verdade (debug).
    NEVER_FAIL_MODE = os.getenv("ROUTER_NEVER_FAIL_MODE", "true").lower() != "false"

    # NOVO: onde persistir strategy_stats / circuit_breaker.
    STATE_DIR = os.getenv("ROUTER_STATE_DIR", "./.router_state")

    # NOVO: TTL de quanto tempo guardamos qual estratégia serviu qual
    # request_id, pra permitir feedback tardio sem crescer sem limite.
    SERVED_REQUEST_TTL = 900


settings = Settings()
os.makedirs(settings.STATE_DIR, exist_ok=True)

# =========================================
# 🧾 LOGGING
# =========================================

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | router | %(message)s")
logger = logging.getLogger("router")

# =========================================
# 📦 INPUT MODELS
# =========================================

class Message(BaseModel):
    role: str
    content: str

    @field_validator("role")
    @classmethod
    def validate_role(cls, v):
        if v not in ("system", "user", "assistant"):
            logger.warning(f"role inválido recebido ({v!r}), normalizando para 'user'")
            return "user"
        return v


class ChatRequest(BaseModel):
    model: Optional[str] = "auto"
    messages: List[Message] = Field(default_factory=list)

    temperature: float = 0.7
    max_tokens: int = settings.DEFAULT_MAX_TOKENS

    stream: bool = False

    @field_validator("temperature", mode="after")
    @classmethod
    def clamp_temperature(cls, v: float) -> float:
        if v is None:
            return 0.7
        return max(settings.TEMPERATURE_MIN, min(float(v), settings.TEMPERATURE_MAX))

    @field_validator("max_tokens", mode="after")
    @classmethod
    def clamp_max_tokens(cls, v: int) -> int:
        if v is None or v <= 0:
            return settings.DEFAULT_MAX_TOKENS
        return max(settings.MAX_TOKENS_FLOOR, min(int(v), settings.MAX_TOKENS_HARD_CAP))


class FeedbackRequest(BaseModel):
    request_id: str
    rating: int  # 1 = bom, -1 = ruim

    @field_validator("rating", mode="after")
    @classmethod
    def clamp_rating(cls, v: int) -> int:
        return 1 if v >= 0 else -1


# =========================================
# 🧠 CORE STRUCTS
# =========================================

@dataclass
class RoutingDecision:
    strategy: str
    task: str
    score: float
    reasoning: str


@dataclass
class ExecutionResult:
    output: str
    latency: float
    strategy: str
    success: bool
    degraded: bool = False


# =========================================
# 💾 PERSISTÊNCIA (NOVO)
# =========================================

def _atomic_save(path, data):
    tmp = path + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.replace(tmp, path)
    except Exception as e:
        logger.warning(f"persist_failed path={path} error={e}")


def _load(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default


_STATS_PATH = os.path.join(settings.STATE_DIR, "strategy_stats.json")
_CB_PATH = os.path.join(settings.STATE_DIR, "circuit_breaker.json")

# =========================================
# 🧼 SANITIZAÇÃO + TRIM DE CONTEXTO
# =========================================

def sanitize_messages(messages: List[Message]) -> List[Dict[str, str]]:
    if not messages:
        raise HTTPException(400, "messages vazio ou ausente")

    cleaned = []
    for m in messages:
        if not m.content:
            continue
        content = str(m.content).strip()
        if not content:
            continue
        if len(content) > settings.MAX_CONTENT_LENGTH:
            content = content[:settings.MAX_CONTENT_LENGTH]
        cleaned.append({"role": m.role, "content": content})

    if not cleaned:
        raise HTTPException(400, "messages inválido (todas as mensagens ficaram vazias após sanitização)")

    return cleaned[-settings.MAX_MESSAGES:]


def trim_messages_by_budget(messages: List[Dict[str, str]], char_budget: int) -> List[Dict[str, str]]:
    """NOVO: mantém as mensagens mais recentes até estourar o orçamento de
    caracteres, sempre preservando a primeira mensagem 'system' (se
    houver) inteira, já que ela carrega instruções e não deve ser podada."""
    if not messages:
        return messages

    system_msgs = [m for m in messages if m["role"] == "system"]
    other_msgs = [m for m in messages if m["role"] != "system"]

    system_chars = sum(len(m["content"]) for m in system_msgs)
    remaining_budget = max(500, char_budget - system_chars)

    kept = []
    total = 0
    for m in reversed(other_msgs):
        total += len(m["content"])
        if total > remaining_budget and kept:
            break
        kept.append(m)

    return system_msgs + list(reversed(kept))


# =========================================
# 🧠 REQUEST CONTEXT
# =========================================

@dataclass
class RequestContext:
    request_id: str
    start_time: float
    user_agent: Optional[str] = None

    def latency(self) -> float:
        return time.time() - self.start_time


def new_context(req: Optional[Request] = None) -> RequestContext:
    return RequestContext(
        request_id=str(uuid.uuid4()),
        start_time=time.time(),
        user_agent=req.headers.get("user-agent") if req else None,
    )


# =========================================
# 🧠 FEATURE EXTRACTION / CLASSIFICAÇÃO
# =========================================

def extract_features(messages: List[Dict[str, str]]) -> Dict[str, Any]:
    text = " ".join([m["content"] for m in messages]).lower()
    return {
        "length": len(text),
        "has_code": any(k in text for k in ["def ", "class ", "import ", "```", "error", "exception", "traceback", "bug", "fix", "stack"]),
        "is_question": "?" in text,
        "complexity": sum([text.count(w) for w in ["porque", "explique", "analise", "compare", "detalhe", "profundo"]]),
        "has_math": any(k in text for k in ["+", "-", "*", "/", "="]),
        "has_logic": any(k in text for k in ["if", "else", "loop", "while"]),
        "keywords": text,
    }


def classify_task(features: Dict[str, Any]) -> str:
    if features["has_code"]:
        return "coding"
    if features["has_math"] or features["has_logic"]:
        return "reasoning"
    if features["length"] > 6000:
        return "long_context"
    if features["complexity"] >= 2:
        return "reasoning"
    if features["is_question"]:
        return "qa"
    return "chat"


STRATEGIES = {
    "fast": {"speed": 10, "cost": 1, "quality": 5},
    "smart": {"speed": 7, "cost": 4, "quality": 8},
    "reasoning": {"speed": 4, "cost": 8, "quality": 10},
}

# =========================================
# 🧠 LEARNING ENGINE (com persistência)
# =========================================

_default_stats = lambda: {"success": 1, "fail": 1, "latency": 1}

strategy_stats: Dict[str, Dict[str, float]] = _load(_STATS_PATH, {
    "fast": _default_stats(), "smart": _default_stats(), "reasoning": _default_stats(),
})
for k in ("fast", "smart", "reasoning"):
    strategy_stats.setdefault(k, _default_stats())

_stats_lock = threading.Lock()


def update_learning(strategy: str, success: bool, latency: float):
    if not settings.ENABLE_LEARNING:
        return
    with _stats_lock:
        data = strategy_stats[strategy]
        if success:
            data["success"] += 1
        else:
            data["fail"] += 1
        data["latency"] = (data["latency"] + latency) / 2


def get_learning_bonus(strategy: str) -> float:
    data = strategy_stats[strategy]
    success_rate = data["success"] / (data["success"] + data["fail"])
    bonus = success_rate * 6
    latency_penalty = min(data["latency"] / 2, 6)
    return bonus - latency_penalty


# =========================================
# 🧠 SCORING
# =========================================

def score_strategy(strategy: str, task: str, features: Dict[str, Any], temperature: float) -> float:
    base = STRATEGIES[strategy]
    score = 0

    if task == "coding":
        score += 12 if strategy == "smart" else (8 if strategy == "reasoning" else 0)
    elif task == "reasoning":
        score += 14 if strategy == "reasoning" else 0
    elif task == "long_context":
        score += 10 if strategy == "smart" else 0
    elif task == "qa":
        score += 8 if strategy == "fast" else 0

    if features["length"] > 4000 and strategy == "fast":
        score -= 6
    if features["complexity"] > 1:
        score += base["quality"]
    if temperature > 0.8:
        score += base["quality"] * 0.6

    score -= base["cost"] * 0.7
    score += get_learning_bonus(strategy)
    return score


# =========================================
# 🧠 CIRCUIT BREAKER (com persistência)
# =========================================

circuit_breaker: Dict[str, Dict[str, Any]] = _load(_CB_PATH, {
    "fast": {"failures": 0, "open_until": 0},
    "smart": {"failures": 0, "open_until": 0},
    "reasoning": {"failures": 0, "open_until": 0},
})
for k in ("fast", "smart", "reasoning"):
    circuit_breaker.setdefault(k, {"failures": 0, "open_until": 0})

_cb_lock = threading.Lock()


def is_circuit_open(strategy: str) -> bool:
    return time.time() < circuit_breaker[strategy]["open_until"]


def record_failure_cb(strategy: str):
    with _cb_lock:
        cb = circuit_breaker[strategy]
        cb["failures"] += 1
        if cb["failures"] >= settings.FAILURE_THRESHOLD:
            cb["open_until"] = time.time() + settings.RECOVERY_TIME
            cb["failures"] = 0
            logger.warning(f"CIRCUIT OPEN: {strategy}")


def record_success_cb(strategy: str):
    with _cb_lock:
        circuit_breaker[strategy]["failures"] = 0


def _persist_learning_state():
    _atomic_save(_STATS_PATH, strategy_stats)
    _atomic_save(_CB_PATH, circuit_breaker)


def _persistence_loop():
    while True:
        time.sleep(20)
        _persist_learning_state()


threading.Thread(target=_persistence_loop, daemon=True).start()
atexit.register(_persist_learning_state)


# =========================================
# 🧠 DECISION ENGINE
# =========================================

def make_routing_decision(messages: List[Dict[str, str]], temperature: float) -> RoutingDecision:
    features = extract_features(messages)
    task = classify_task(features)

    scores = {}
    for strat in STRATEGIES.keys():
        if is_circuit_open(strat):
            continue
        scores[strat] = score_strategy(strat, task, features, temperature)

    if not scores:
        # Todos os circuitos abertos ao mesmo tempo (provider caiu de
        # vez). Em vez de travar até o RECOVERY_TIME expirar sozinho,
        # força reset parcial da estratégia mais barata pra dar uma
        # chance de recuperação.
        logger.error("Todas as estratégias com circuito aberto — forçando reset de 'fast'")
        circuit_breaker["fast"]["open_until"] = 0
        circuit_breaker["fast"]["failures"] = 0
        scores["fast"] = score_strategy("fast", task, features, temperature)

    best = max(scores, key=scores.get)
    logger.info(f"DECISION | task={task} | scores={scores} | chosen={best}")

    return RoutingDecision(strategy=best, task=task, score=scores[best], reasoning=str(scores))


# =========================================
# 🚀 GATEWAY BRIDGE
# =========================================

def call_gateway(messages, temperature, max_tokens) -> str:
    try:
        response = execute_protected(messages, temperature=temperature, max_tokens=max_tokens)
        if not response:
            raise Exception("empty_response")
        return str(response)
    except NoProvidersAvailableError as e:
        raise Exception(f"no_providers_available: {e}")
    except GatewayError as e:
        raise Exception(f"gateway_error: {e}")
    except Exception as e:
        raise Exception(f"gateway_error: {e}")


# =========================================
# 🧠 RESPONSE VALIDATION (CORRIGIDO)
# =========================================
#
# BUG CRÍTICO CORRIGIDO: a versão anterior rejeitava qualquer resposta
# contendo palavras como "error"/"exception"/"failed" no TEXTO da
# resposta — o que descarta respostas legítimas sempre que o usuário
# está falando sobre bugs/erros (exatamente o caso de uso do Hermes).
# Validação agora é estrutural (vazio / curto demais), não léxica.

def validate_response(text: str) -> bool:
    if not text:
        return False
    t = text.strip()
    if len(t) < 2:
        return False
    return True


# =========================================
# 🧠 STRATEGY EXECUTORS
# =========================================

def _safe_tokens(v: int) -> int:
    return max(settings.MAX_TOKENS_FLOOR, min(int(v), settings.MAX_TOKENS_HARD_CAP))


def execute_fast(messages, temperature, max_tokens):
    adjusted = _safe_tokens(max(int(max_tokens * 0.7), 64))
    return call_gateway(messages, temperature * 0.7, adjusted)


def execute_smart(messages, temperature, max_tokens):
    return call_gateway(messages, temperature, _safe_tokens(max_tokens))


def execute_reasoning(messages, temperature, max_tokens):
    adjusted = _safe_tokens(int(max_tokens * 1.2))
    return call_gateway(messages, temperature * 0.5, adjusted)


STRATEGY_EXECUTORS = {"fast": execute_fast, "smart": execute_smart, "reasoning": execute_reasoning}


def run_with_retries(strategy, messages, temperature, max_tokens):
    executor_fn = STRATEGY_EXECUTORS[strategy]
    last_error = None

    for attempt in range(settings.MAX_STRATEGY_RETRIES):
        try:
            result = executor_fn(messages, temperature, max_tokens)
            if validate_response(result):
                return result
            last_error = "invalid_response(empty_or_too_short)"
        except Exception as e:
            last_error = str(e)
        time.sleep(0.3 * (attempt + 1))

    raise Exception(f"{strategy}_failed: {last_error}")


def fallback_chain(primary_strategy):
    order = ["fast", "smart", "reasoning"]
    order.remove(primary_strategy)
    return [primary_strategy] + order


# =========================================
# 🚀 EXECUTE WITH STRATEGY (nunca estoura 502 se NEVER_FAIL_MODE)
# =========================================

_DEGRADED_MESSAGE = (
    "Não consegui falar com nenhum provedor de modelo agora (todos "
    "indisponíveis ou com erro). Isso é temporário — tente de novo em "
    "alguns segundos. [resposta de degradação automática]"
)


def execute_with_strategy(decision: RoutingDecision, messages, temperature, max_tokens) -> ExecutionResult:
    strategies = fallback_chain(decision.strategy)
    last_error = "unknown"

    for strat in strategies:
        if is_circuit_open(strat):
            continue

        start = time.time()
        try:
            result = run_with_retries(strat, messages, temperature, max_tokens)
            latency = time.time() - start

            record_success_cb(strat)
            update_learning(strat, True, latency)
            logger.info(f"SUCCESS | strat={strat} | latency={latency:.2f}s")

            return ExecutionResult(output=result, latency=latency, strategy=strat, success=True)

        except Exception as e:
            latency = time.time() - start
            last_error = str(e)
            record_failure_cb(strat)
            update_learning(strat, False, latency)
            logger.warning(f"FAIL | strat={strat} | error={e}")
            continue

    # Todas as estratégias falharam de verdade.
    if settings.NEVER_FAIL_MODE:
        logger.error(f"ALL_STRATEGIES_FAILED | last_error={last_error} | devolvendo resposta degradada (200)")
        return ExecutionResult(output=_DEGRADED_MESSAGE, latency=0.0, strategy="degraded", success=False, degraded=True)

    raise HTTPException(502, f"all_strategies_failed: {last_error}")


# =========================================
# 🚀 GLOBAL REQUEST CONTROL
# =========================================

active_requests = 0
MAX_CONCURRENT_REQUESTS = 100

# =========================================
# 📇 SERVED-REQUEST TRACKER (para /feedback)
# =========================================

served_requests: Dict[str, Dict[str, Any]] = {}
_served_lock = threading.Lock()


def _record_served(request_id: str, strategy: str, latency: float):
    with _served_lock:
        served_requests[request_id] = {"strategy": strategy, "latency": latency, "time": time.time()}
        # limpeza simples por TTL pra não crescer sem limite
        if len(served_requests) > 5000:
            cutoff = time.time() - settings.SERVED_REQUEST_TTL
            for k in [k for k, v in served_requests.items() if v["time"] < cutoff]:
                served_requests.pop(k, None)


# =========================================
# 🧠 EXECUTION WRAPPER (ASYNC + TIMEOUT)
# =========================================

async def safe_execute(decision: RoutingDecision, messages, temperature, max_tokens, context: RequestContext) -> ExecutionResult:
    loop = asyncio.get_event_loop()
    try:
        result: ExecutionResult = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: execute_with_strategy(decision, messages, temperature, max_tokens)),
            timeout=settings.REQUEST_TIMEOUT,
        )
        _record_served(context.request_id, result.strategy, result.latency)
        return result

    except asyncio.TimeoutError:
        logger.error(f"TIMEOUT | request_id={context.request_id}")
        if settings.NEVER_FAIL_MODE:
            return ExecutionResult(output=_DEGRADED_MESSAGE, latency=settings.REQUEST_TIMEOUT, strategy="degraded", success=False, degraded=True)
        raise HTTPException(504, "timeout")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"EXECUTION ERROR | {e}")
        if settings.NEVER_FAIL_MODE:
            return ExecutionResult(output=_DEGRADED_MESSAGE, latency=0.0, strategy="degraded", success=False, degraded=True)
        raise HTTPException(500, "execution_failed")


# =========================================
# 🧠 RESPONSE FORMATTERS
# =========================================

def build_response(result: ExecutionResult, context: RequestContext):
    return {
        "id": context.request_id,
        "object": "chat.completion",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": result.output}}],
        "meta": {
            "strategy": result.strategy,
            "latency": round(result.latency, 3),
            "total_time": round(context.latency(), 3),
            "degraded": result.degraded,
        },
    }


def build_openai_response(result: ExecutionResult, context: RequestContext, model_name: str = "router"):
    completion_tokens = len(result.output.split())
    return {
        "id": f"chatcmpl-{context.request_id}",
        "object": "chat.completion",
        "created": int(context.start_time),
        "model": model_name,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": result.output},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": completion_tokens, "total_tokens": completion_tokens},
        # campo extra não-padrão, mas inofensivo para clientes OpenAI-compat
        # que simplesmente ignoram chaves desconhecidas.
        "router_meta": {"strategy": result.strategy, "degraded": result.degraded},
    }


def build_openai_error(message: str, error_type: str = "invalid_request_error", code: Optional[str] = None):
    return {"error": {"message": message, "type": error_type, "code": code}}


# =========================================
# 🧠 CACHE (nível 2, resposta completa)
# =========================================

class ResponseCache:

    def __init__(self):
        self.store = {}
        self.lock = asyncio.Lock()

    def _make_key(self, messages, temperature, max_tokens):
        raw = str(messages) + str(temperature) + str(max_tokens)
        return hashlib.sha256(raw.encode()).hexdigest()

    async def get(self, key):
        async with self.lock:
            data = self.store.get(key)
            if not data:
                return None
            if time.time() - data["time"] > settings.CACHE_TTL:
                del self.store[key]
                return None
            return data["value"]

    async def set(self, key, value):
        async with self.lock:
            if len(self.store) > settings.MAX_CACHE_SIZE:
                self.store.pop(next(iter(self.store)))
            self.store[key] = {"value": value, "time": time.time()}


response_cache = ResponseCache()


def semantic_hash(messages):
    text = " ".join([m["content"] for m in messages]).lower()
    for k in ["o", "a", "de", "do", "da", "e"]:
        text = text.replace(f" {k} ", " ")
    return hashlib.md5(text.encode()).hexdigest()


semantic_store = {}


def semantic_get(messages):
    return semantic_store.get(semantic_hash(messages))


def semantic_set(messages, value):
    semantic_store[semantic_hash(messages)] = value
    # NOVO: evita crescimento ilimitado do cache semântico.
    if len(semantic_store) > settings.MAX_CACHE_SIZE:
        semantic_store.pop(next(iter(semantic_store)))


# =========================================
# 🧠 RANKING (execução paralela)
# =========================================

def rank_outputs(outputs: List[str]) -> str:
    def score(text):
        if not text:
            return 0
        s = len(text)
        if len(text.split()) < 5:
            s -= 50
        return s
    return sorted(outputs, key=score, reverse=True)[0]


async def parallel_execute(messages, temperature, max_tokens):
    loop = asyncio.get_event_loop()
    strategies = ["fast", "smart"]
    tasks = []
    for strat in strategies:
        decision = RoutingDecision(strategy=strat, task="parallel", score=0, reasoning="parallel")
        tasks.append(loop.run_in_executor(None, lambda d=decision: execute_with_strategy(d, messages, temperature, max_tokens)))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    candidates = [(r.output, r.strategy) for r in results if isinstance(r, ExecutionResult) and r.success]

    if not candidates:
        if settings.NEVER_FAIL_MODE:
            return _DEGRADED_MESSAGE, "degraded"
        raise Exception("parallel_failed")

    best_output = rank_outputs([o for o, _ in candidates])
    best_strategy = next((s for o, s in candidates if o == best_output), "parallel")
    return best_output, best_strategy


# =========================================
# 🌊 STREAMING (SSE)
# =========================================

async def stream_response(text: str):
    for token in text.split():
        yield f"data: {json.dumps({'token': token})}\n\n"
        await asyncio.sleep(0.01)
    yield "data: [DONE]\n\n"


async def stream_openai_response(result: ExecutionResult, context: RequestContext, model_name: str):
    created = int(context.start_time)
    for token in result.output.split():
        chunk = {
            "id": f"chatcmpl-{context.request_id}", "object": "chat.completion.chunk",
            "created": created, "model": model_name,
            "choices": [{"index": 0, "delta": {"content": token + " "}, "finish_reason": None}],
        }
        yield f"data: {json.dumps(chunk)}\n\n"
        await asyncio.sleep(0.01)

    final_chunk = {
        "id": f"chatcmpl-{context.request_id}", "object": "chat.completion.chunk",
        "created": created, "model": model_name,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    yield f"data: {json.dumps(final_chunk)}\n\n"
    yield "data: [DONE]\n\n"


# =========================================
# 🧠 ANTI-SPAM / LOOP PROTECTION
# =========================================

recent_requests = defaultdict(list)


def is_spam(user_id, content):
    now = time.time()
    history = recent_requests[user_id]
    history.append((content, now))
    recent_requests[user_id] = [(c, t) for c, t in history if now - t < 10]
    texts = [c for c, _ in recent_requests[user_id]]
    return texts.count(content) > 3


# =========================================
# 🚀 WARMUP
# =========================================

def warmup():
    try:
        execute_protected([{"role": "user", "content": "ping"}], temperature=0.1, max_tokens=5)
        logger.info("WARMUP OK")
    except Exception as e:
        logger.warning(f"WARMUP FAIL: {e}")


threading.Thread(target=warmup, daemon=True).start()


# =========================================
# ❤️ HEALTH / 📊 METRICS / 📋 STATUS
# =========================================

@app.get("/health")
def health_endpoint():
    return {"status": "ok", "service": "router", "version": "6.0", "time": time.time()}


@app.get("/metrics")
def metrics_endpoint():
    try:
        return {"models": gateway_metrics.snapshot(), "gateway_health": gateway_health_status()}
    except Exception as e:
        logger.error(f"metrics error: {e}")
        return JSONResponse(status_code=500, content={"error": "metrics_failure"})


@app.get("/status")
def status_endpoint():
    return {
        "router": {
            "active_requests": active_requests,
            "max_concurrent": MAX_CONCURRENT_REQUESTS,
            "learning": strategy_stats,
            "circuit": circuit_breaker,
            "never_fail_mode": settings.NEVER_FAIL_MODE,
        },
        "gateway": {
            "models": gateway_metrics.snapshot(),
            "health": gateway_health_status(),
            "config": {
                "timeout": GATEWAY_CONFIG.timeout,
                "max_attempts": GATEWAY_CONFIG.max_attempts,
                "cache_enabled": GATEWAY_CONFIG.cache_enabled,
            },
        },
    }


@app.get("/")
def root():
    return {"service": "hermes-router", "status": "ok", "version": "6.0"}


# =========================================
# 🗳️ FEEDBACK (NOVO)
# =========================================

@app.post("/feedback")
def feedback_endpoint(fb: FeedbackRequest):
    with _served_lock:
        served = served_requests.get(fb.request_id)

    if not served:
        # Não é erro fatal — só não tem o que aprender com isso.
        return {"status": "ignored", "reason": "request_id não encontrado ou expirado"}

    update_learning(served["strategy"], success=(fb.rating > 0), latency=served["latency"])
    logger.info(f"FEEDBACK | request_id={fb.request_id} | strategy={served['strategy']} | rating={fb.rating}")
    return {"status": "ok", "strategy": served["strategy"], "rating": fb.rating}


# =========================================
# 🚀 MAIN ENDPOINT /CHAT
# =========================================

@app.post("/chat")
async def chat(request: ChatRequest, req: Request):
    global active_requests

    user_id = req.client.host if req.client else "anon"

    if is_spam(user_id, str(request.messages)):
        raise HTTPException(429, "spam_detected")

    if active_requests >= MAX_CONCURRENT_REQUESTS:
        raise HTTPException(429, "server_overloaded")

    active_requests += 1
    context = new_context(req)

    try:
        messages = sanitize_messages(request.messages)
        messages = trim_messages_by_budget(messages, settings.CONTEXT_CHAR_BUDGET)

        max_tokens = min(request.max_tokens, settings.MAX_TOKENS_HARD_CAP)

        cache_key = response_cache._make_key(messages, request.temperature, max_tokens)
        cached = await response_cache.get(cache_key)
        if cached:
            logger.info("CACHE HIT")
            result = ExecutionResult(output=cached["output"], latency=0.0, strategy=cached["strategy"], success=True)
            return build_response(result, context)

        sem = semantic_get(messages)
        if sem:
            logger.info("SEMANTIC CACHE HIT")
            result = ExecutionResult(output=sem["output"], latency=0.0, strategy=sem["strategy"], success=True)
            return build_response(result, context)

        decision = make_routing_decision(messages, request.temperature)

        if decision.strategy == "smart" and request.temperature < 0.5:
            output, used_strategy = await parallel_execute(messages, request.temperature, max_tokens)
            result = ExecutionResult(output=output, latency=context.latency(), strategy=used_strategy, success=True)
        else:
            result = await safe_execute(decision, messages, request.temperature, max_tokens, context)

        if not result.degraded:
            cache_payload = {"output": result.output, "strategy": result.strategy}
            await response_cache.set(cache_key, cache_payload)
            semantic_set(messages, cache_payload)

        if request.stream:
            return JSONResponse(content={"stream": "use /stream endpoint"}, status_code=200)

        response = build_response(result, context)
        logger.info(f"REQUEST OK | id={context.request_id} | strat={result.strategy} | time={context.latency():.2f}s")
        return response

    except HTTPException as e:
        logger.warning(f"HTTP ERROR | id={context.request_id} | code={e.status_code} | detail={e.detail}")
        raise e
    except Exception:
        logger.error(f"FATAL ERROR | id={context.request_id} | {traceback.format_exc()}")
        if settings.NEVER_FAIL_MODE:
            result = ExecutionResult(output=_DEGRADED_MESSAGE, latency=0.0, strategy="degraded", success=False, degraded=True)
            return build_response(result, context)
        raise HTTPException(500, "internal_error")
    finally:
        active_requests -= 1


@app.post("/debug/decision")
async def debug_decision(request: ChatRequest):
    messages = sanitize_messages(request.messages)
    decision = make_routing_decision(messages, request.temperature)
    return {"strategy": decision.strategy, "task": decision.task, "score": decision.score, "reasoning": decision.reasoning}


@app.post("/stream")
async def stream_chat(request: ChatRequest):
    messages = sanitize_messages(request.messages)
    messages = trim_messages_by_budget(messages, settings.CONTEXT_CHAR_BUDGET)
    decision = make_routing_decision(messages, request.temperature)

    result = await safe_execute(decision, messages, request.temperature, request.max_tokens, new_context())
    return StreamingResponse(stream_response(result.output), media_type="text/event-stream")


# =========================================
# 🔌 OPENAI COMPAT
# =========================================

@app.post("/chat/completions")
@app.post("/v1/chat/completions")
async def openai_chat_completions(request: ChatRequest, req: Request):
    context = new_context(req)

    messages = sanitize_messages(request.messages)
    messages = trim_messages_by_budget(messages, settings.CONTEXT_CHAR_BUDGET)

    decision = make_routing_decision(messages, request.temperature)
    result = await safe_execute(decision, messages, request.temperature, request.max_tokens, context)

    if request.stream:
        return StreamingResponse(stream_openai_response(result, context, "router"), media_type="text/event-stream")

    return build_openai_response(result, context, "router")


# =========================================
# 📦 MODELS ENDPOINT (OpenAI + Ollama compat)
# =========================================

_MODEL_INFO = {"id": "router", "object": "model", "owned_by": "local", "created": int(time.time())}


@app.get("/v1/models")
@app.get("/models")
@app.get("/api/v1/models")
def list_models():
    return {"object": "list", "data": [_MODEL_INFO]}


@app.get("/v1/models/{model_id}")
def get_model(model_id: str):
    return {**_MODEL_INFO, "id": model_id}


@app.get("/api/tags")
def ollama_tags():
    return {"models": [{
        "name": "router:latest", "model": "router:latest",
        "modified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "size": 0, "digest": "local",
    }]}


@app.post("/api/show")
async def ollama_show(req: Request):
    body = {}
    try:
        body = await req.json()
    except Exception:
        pass
    return {
        "modelfile": "", "parameters": "", "template": "",
        "details": {"family": "router", "parameter_size": "n/a", "quantization_level": "n/a"},
        "model_info": {"name": body.get("name", "router")},
    }


@app.get("/version")
def version():
    return {"version": "router-6.0"}


@app.get("/props")
@app.get("/v1/props")
def props():
    return {"name": "router", "type": "openai-compatible"}


# =========================================
# 🛡️ EXCEPTION HANDLERS GLOBAIS
# =========================================

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(f"VALIDATION ERROR | path={request.url.path} | errors={exc.errors()}")
    return JSONResponse(
        status_code=400,
        content=build_openai_error(message=f"Requisição inválida: {exc.errors()}", error_type="invalid_request_error", code="validation_error"),
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(f"UNHANDLED ERROR | path={request.url.path} | {traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content=build_openai_error(message="internal_error", error_type="server_error", code="internal_error"),
    )
