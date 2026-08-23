import os
import time
import json
import random
import hashlib
import logging
import itertools
import threading
import atexit
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, Future

import requests
from dotenv import load_dotenv

# ============================================================
# ENV
# ============================================================

load_dotenv()

# ============================================================
# LOGGER
# ============================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gateway")


def log_event(level, message, **kwargs):
    log = {"time": time.time(), "level": level, "msg": message, **kwargs}
    print(json.dumps(log))


import uuid


def new_request_id():
    return str(uuid.uuid4())


# ============================================================
# GLOBAL CONFIG
# ============================================================

@dataclass
class GatewayConfig:
    timeout: int = 60
    max_attempts: int = 10

    cache_enabled: bool = True
    cache_ttl: int = 600

    failure_threshold: int = 3
    cooldown_seconds: int = 60

    max_retry_delay: int = 20

    # NOVO: raiz do estado persistido (metrics/health/timeouts) em disco.
    state_dir: str = os.getenv("GATEWAY_STATE_DIR", "./.gateway_state")
    persist_every_seconds: int = 20

    # NOVO: quantas entradas (provider,model,key) manter no máximo em
    # cada estrutura antes de podar as mais antigas/inativas.
    max_tracked_entries: int = 500

    # NOVO (v3): teto de defesa-em-profundidade pra max_tokens, aplicado
    # DENTRO do próprio execute() — não depende do router já ter
    # clampado. Protege o gateway se algum dia for chamado direto (ex.:
    # teste manual em /chat sem passar pelo router). 8192 é um teto
    # seguro pra maioria dos modelos Groq/OpenRouter/Gemini de hoje;
    # ajuste via env se precisar de mais.
    max_tokens_hard_cap: int = int(os.getenv("GATEWAY_MAX_TOKENS_CAP", "8192"))

    # NOVO (v3): auth opcional pro gateway standalone.
    require_auth: bool = os.getenv("GATEWAY_REQUIRE_AUTH", "false").lower() == "true"
    api_key: str = os.getenv("GATEWAY_API_KEY", "")

    # NOVO (v3): CORS opcional (lista separada por vírgula, ou "*").
    cors_origins: str = os.getenv("GATEWAY_CORS_ORIGINS", "")


CONFIG = GatewayConfig()
os.makedirs(CONFIG.state_dir, exist_ok=True)

# ============================================================
# PROVIDER MODEL
# ============================================================

@dataclass
class ProviderConfig:
    name: str
    priority: int
    type: str
    url: str
    keys: List[str]
    models: List[str]


PROVIDERS: Dict[str, ProviderConfig] = {
    "groq": ProviderConfig(
        name="groq", priority=1, type="openai",
        url="https://api.groq.com/openai/v1/chat/completions",
        keys=[os.getenv("GROQ_KEY_1"), os.getenv("GROQ_KEY_2"), os.getenv("GROQ_KEY_3")],
        models=[
            "llama-3.1-8b-instant", "llama-3.3-70b-versatile",
            "openai/gpt-oss-20b", "openai/gpt-oss-120b",
            "qwen/qwen3-32b", "qwen/qwen3.6-27b",
            "meta-llama/llama-4-scout-17b-16e-instruct",
            "groq/compound", "groq/compound-mini",
        ],
    ),
    "openrouter": ProviderConfig(
        name="openrouter", priority=2, type="openai",
        url="https://openrouter.ai/api/v1/chat/completions",
        keys=[os.getenv("OPENROUTER_KEY_1"), os.getenv("OPENROUTER_KEY_2"), os.getenv("OPENROUTER_KEY_3")],
        models=[
            "openai/gpt-oss-120b:free", "openai/gpt-oss-20b:free",
            "qwen/qwen3-coder:free", "qwen/qwen3-next-80b-a3b-instruct:free",
            "nousresearch/hermes-3-llama-3.1-405b:free",
            "nvidia/nemotron-3-super-120b-a12b:free",
            "nvidia/nemotron-3-ultra-550b-a55b:free",
            "meta-llama/llama-3.3-70b-instruct:free",
            "google/gemma-4-31b-it:free", "google/gemma-4-26b-a4b-it:free",
        ],
    ),
    "gemini": ProviderConfig(
        name="gemini", priority=3, type="gemini",
        url="https://generativelanguage.googleapis.com/v1beta/models",
        keys=[os.getenv("GEMINI_KEY_1"), os.getenv("GEMINI_KEY_2")],
        models=["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash"],
    ),
}

_total_keys = sum(1 for p in PROVIDERS.values() for k in p.keys if k)
if _total_keys == 0:
    log_event("WARN", "no_provider_keys_configured",
              detail="Nenhuma API key encontrada no .env. Todas as chamadas vão falhar.")
else:
    log_event("INFO", "providers_loaded", total_keys=_total_keys)


# ============================================================
# REQUEST CONTEXT
# ============================================================

@dataclass
class RequestContext:
    request_id: str
    start_time: float
    provider: Optional[str] = None
    model: Optional[str] = None
    attempt: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def latency(self) -> float:
        return time.time() - self.start_time


# ============================================================
# STATE PERSISTENCE (NOVO)
# ============================================================

class PersistentJSON:
    """Pequeno helper de load/save atômico em JSON, tolerante a falhas."""

    def __init__(self, path: str):
        self.path = path
        self.lock = threading.Lock()

    def load(self, default):
        try:
            with open(self.path, "r") as f:
                return json.load(f)
        except Exception:
            return default

    def save(self, data):
        tmp = self.path + ".tmp"
        try:
            with self.lock:
                with open(tmp, "w") as f:
                    json.dump(data, f)
                os.replace(tmp, self.path)
        except Exception as e:
            log_event("WARN", "persist_failed", path=self.path, error=str(e))


_metrics_store = PersistentJSON(os.path.join(CONFIG.state_dir, "metrics.json"))
_health_store = PersistentJSON(os.path.join(CONFIG.state_dir, "health.json"))
_timeouts_store = PersistentJSON(os.path.join(CONFIG.state_dir, "timeouts.json"))


# ============================================================
# THREAD-SAFE CACHE
# ============================================================

class SmartCache:

    def __init__(self):
        self.store = {}
        self.lock = threading.Lock()

    def make_key(self, model, messages, extra=None):
        raw = json.dumps({"model": model, "messages": messages, "extra": extra or {}}, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, key):
        with self.lock:
            data = self.store.get(key)
            if not data:
                return None
            if time.time() - data["time"] > CONFIG.cache_ttl:
                del self.store[key]
                return None
            return data["value"]

    def set(self, key, value):
        with self.lock:
            self.store[key] = {"value": value, "time": time.time()}


CACHE = SmartCache()

# ============================================================
# METRICS ENGINE
# ============================================================

class Metrics:

    def __init__(self):
        raw = _metrics_store.load({})
        self.data = defaultdict(lambda: {"success": 1, "fail": 1, "latency": 1.0})
        for k, v in raw.items():
            self.data[tuple(k.split("::", 1))] = v

    def update(self, provider, model, success, latency):
        m = self.data[(provider, model)]
        if success:
            m["success"] += 1
        else:
            m["fail"] += 1
        if latency > 0:
            m["latency"] = (m["latency"] + latency) / 2
        self._prune()

    def score(self, provider, model):
        m = self.data[(provider, model)]
        success_rate = m["success"] / (m["success"] + m["fail"])
        latency = max(m["latency"], 0.1)
        return (success_rate * 10) / latency

    def _prune(self):
        # Evita crescimento ilimitado se muitos provider:model diferentes
        # forem testados ao longo da vida do processo.
        if len(self.data) > CONFIG.max_tracked_entries:
            worst = sorted(self.data.items(), key=lambda kv: kv[1]["success"])[:50]
            for k, _ in worst:
                self.data.pop(k, None)

    def snapshot(self):
        return {f"{p}:{m}": v for (p, m), v in self.data.items()}

    def persist(self):
        _metrics_store.save({f"{p}::{m}": v for (p, m), v in self.data.items()})


metrics = Metrics()

# ============================================================
# CIRCUIT BREAKER + HEALTH ENGINE
# ============================================================

class CircuitState:
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class HealthState:
    failures: int = 0
    last_failure: float = 0
    cooldown_until: float = 0
    state: str = CircuitState.CLOSED
    success_streak: int = 0


class HealthEngine:
    """Nome `health_engine` (não `health`) de propósito: evita shadowing
    contra endpoints/rotas chamados `health()` em outros módulos."""

    def __init__(self):
        self.states: Dict[str, HealthState] = {}
        self.lock = threading.Lock()
        raw = _health_store.load({})
        for k, v in raw.items():
            self.states[k] = HealthState(**v)

    def _key(self, provider, api_key, model):
        # Mascara a key nos logs/estado persistido — não guardamos a key
        # inteira em disco por segurança básica.
        masked = (api_key or "")[:6]
        return f"{provider}:{masked}:{model}"

    def _get(self, key):
        if key not in self.states:
            self.states[key] = HealthState()
        return self.states[key]

    def is_available(self, provider, api_key, model):
        key = self._key(provider, api_key, model)
        with self.lock:
            state = self._get(key)
            now = time.time()
            if state.state == CircuitState.OPEN:
                if now >= state.cooldown_until:
                    state.state = CircuitState.HALF_OPEN
                    logger.info(f"[RECOVERY] {key} -> HALF_OPEN")
                    return True
                return False
            return True

    def on_failure(self, provider, api_key, model, error):
        key = self._key(provider, api_key, model)
        with self.lock:
            state = self._get(key)
            state.failures += 1
            state.last_failure = time.time()
            state.success_streak = 0

            penalty = min(300, CONFIG.cooldown_seconds * state.failures)
            # jitter de recovery: evita que todas as chaves reabram no
            # mesmo segundo exato (thundering herd contra o provider).
            penalty += random.uniform(0, penalty * 0.15)
            state.cooldown_until = time.time() + penalty

            if state.failures >= CONFIG.failure_threshold:
                state.state = CircuitState.OPEN
                logger.warning(f"[CIRCUIT OPEN] {key} | penalty={penalty:.1f}s")

    def on_success(self, provider, api_key, model):
        key = self._key(provider, api_key, model)
        with self.lock:
            state = self._get(key)
            state.success_streak += 1
            state.failures = 0
            if state.state == CircuitState.HALF_OPEN:
                if state.success_streak >= 2:
                    state.state = CircuitState.CLOSED
                    logger.info(f"[CIRCUIT CLOSED] {key}")

    def health_score(self, provider, api_key, model):
        key = self._key(provider, api_key, model)
        state = self._get(key)
        if state.state == CircuitState.OPEN:
            return 0
        penalty = 1 + state.failures
        bonus = 1 + state.success_streak
        return bonus / penalty

    def persist(self):
        with self.lock:
            _health_store.save({k: vars(v) for k, v in self.states.items()})


health_engine = HealthEngine()

# ============================================================
# KEY ROTATION
# ============================================================

class KeyManager:

    def __init__(self):
        self.usage = defaultdict(int)
        self.lock = threading.Lock()

    def _valid_keys(self, provider: ProviderConfig, model: str):
        return [k for k in provider.keys if k and health_engine.is_available(provider.name, k, model)]

    def _best_key(self, provider: ProviderConfig, model: str):
        valid_keys = self._valid_keys(provider, model)
        if not valid_keys:
            return None
        with self.lock:
            scored = [
                (k, health_engine.health_score(provider.name, k, model) - (self.usage[(provider.name, k)] * 0.01))
                for k in valid_keys
            ]
        scored.sort(key=lambda x: -x[1])
        return scored[0][0]

    def peek_key(self, provider: ProviderConfig, model: str):
        return self._best_key(provider, model)

    def reserve_key(self, provider: ProviderConfig, key: str):
        with self.lock:
            self.usage[(provider.name, key)] += 1

    def pick_key(self, provider: ProviderConfig, model: str):
        key = self.peek_key(provider, model)
        if key:
            self.reserve_key(provider, key)
        return key


key_manager = KeyManager()


def rank_attempts():
    attempts = []
    for provider in PROVIDERS.values():
        for model in provider.models:
            key = key_manager.peek_key(provider, model)
            if not key:
                continue
            score = (
                provider.priority * -1
                + metrics.score(provider.name, model)
                + health_engine.health_score(provider.name, key, model)
            )
            attempts.append({"provider": provider, "model": model, "key": key, "score": score})
    attempts.sort(key=lambda x: -x["score"])
    return attempts


# ============================================================
# ERRORS
# ============================================================

class GatewayError(Exception):
    pass


class RateLimitError(GatewayError):
    pass


class ProviderError(GatewayError):
    pass


class GatewayTimeoutError(GatewayError):
    """Nome não-nativo de propósito (não sobrescreve o TimeoutError builtin)."""
    pass


class NoProvidersAvailableError(GatewayError):
    """NOVO: erro específico para quando não existe NENHUMA key configurada
    ou todas estão com circuito aberto — permite ao router dar uma
    mensagem melhor do que um genérico 'all_failed'."""
    pass


# ============================================================
# TIMEOUT ADAPTATIVO
# ============================================================

class TimeoutManager:

    def __init__(self):
        self.base = CONFIG.timeout
        raw = _timeouts_store.load({})
        self.history = defaultdict(lambda: self.base)
        for k, v in raw.items():
            self.history[tuple(k.split("::", 1))] = v

    def get(self, provider, model):
        return min(max(5, self.history[(provider, model)]), 120)

    def update(self, provider, model, latency, success):
        key = (provider, model)
        current = self.history[key]
        self.history[key] = (current + latency) / 2 if success else min(120, current * 1.5)

    def snapshot(self):
        return {f"{p}:{m}": v for (p, m), v in self.history.items()}

    def persist(self):
        _timeouts_store.save({f"{p}::{m}": v for (p, m), v in self.history.items()})


timeout_manager = TimeoutManager()


def compute_backoff(attempt):
    base = 0.5
    delay = min(CONFIG.max_retry_delay, base * (2 ** attempt))
    jitter = delay * 0.2
    return delay + random.uniform(-jitter, jitter)


# ============================================================
# RESPONSE PARSERS
# ============================================================

def safe_extract_text(data):
    try:
        return data["choices"][0]["message"]["content"]
    except Exception:
        pass
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        pass
    return json.dumps(data)


def build_openai_payload(model, messages, temperature=0.7, max_tokens=None):
    payload = {"model": model, "messages": messages, "temperature": temperature}
    if max_tokens:
        payload["max_tokens"] = max_tokens
    return payload


def build_gemini_payload(model, messages, temperature=0.7, max_tokens=None):
    role_map = {"user": "user", "assistant": "model", "model": "model"}
    contents, system_parts = [], []
    for m in messages:
        role = m.get("role", "user")
        if role == "system":
            system_parts.append(m["content"])
            continue
        contents.append({"role": role_map.get(role, "user"), "parts": [{"text": m["content"]}]})
    payload = {"contents": contents, "generationConfig": {"temperature": temperature}}
    if max_tokens:
        payload["generationConfig"]["maxOutputTokens"] = max_tokens
    if system_parts:
        payload["systemInstruction"] = {"parts": [{"text": "\n".join(system_parts)}]}
    return payload


# ============================================================
# HTTP CLIENT
# ============================================================

session = requests.Session()
session.headers.update({"Content-Type": "application/json"})


def send_request(provider: ProviderConfig, model, key, payload, timeout):
    headers = {"Content-Type": "application/json"}
    if provider.type == "openai":
        headers["Authorization"] = f"Bearer {key}"

    url = provider.url
    if provider.type == "gemini":
        url = f"{provider.url}/{model}:generateContent?key={key}"

    for attempt in range(2):
        try:
            response = session.post(url, headers=headers, json=payload, timeout=timeout)

            if response.status_code == 429:
                raise RateLimitError()
            if response.status_code >= 500:
                raise ProviderError(f"http_{response.status_code}")
            if response.status_code >= 400:
                # NOVO: 4xx diferente de 429 (payload rejeitado etc.) não
                # deve ser tratado como "vale a pena tentar de novo" — mas
                # também não pode virar um crash silencioso. Log + erro
                # tipado pra métricas refletirem a causa real.
                raise ProviderError(f"http_{response.status_code}: {response.text[:200]}")

            data = response.json()
            text = safe_extract_text(data)

            if not text or len(text.strip()) == 0:
                raise ProviderError("empty_response")

            return text

        except requests.Timeout:
            if attempt == 1:
                raise GatewayTimeoutError()
        except requests.RequestException as e:
            if attempt == 1:
                raise ProviderError(str(e))

    raise ProviderError("send_request_exhausted_retries")


# ============================================================
# CORE EXECUTION
# ============================================================

def execute(messages: List[Dict[str, str]], temperature: float = 0.7, max_tokens: Optional[int] = None) -> str:
    context = RequestContext(request_id=new_request_id(), start_time=time.time())

    # Defesa-em-profundidade: clampa aqui TAMBÉM, mesmo que quem chamou
    # (o router, ou um cliente direto) já devesse ter feito isso. Isso é
    # o que resolve de vez o padrão de erro "max_tokens=65536 quebra o
    # provider" se o gateway algum dia for exposto/chamado sem o router
    # na frente.
    if max_tokens is not None and max_tokens > CONFIG.max_tokens_hard_cap:
        log_event("WARN", "max_tokens_clamped", requested=max_tokens, clamped_to=CONFIG.max_tokens_hard_cap)
        max_tokens = CONFIG.max_tokens_hard_cap

    cache_key = CACHE.make_key("auto", messages, {"temperature": temperature, "max_tokens": max_tokens})

    if CONFIG.cache_enabled:
        cached = cache_get(cache_key)
        if cached:
            log_event("INFO", "cache_hit", request_id=context.request_id)
            return cached

    attempts = rank_attempts()
    if not attempts:
        # NOVO: erro específico em vez de estourar "all_failed" com
        # last_error=None, o que antes gerava mensagens confusas tipo
        # "all_failed | None".
        raise NoProvidersAvailableError(
            "Nenhum provider disponível (sem keys configuradas ou todos os circuitos abertos)."
        )

    last_error = None

    for i, attempt in enumerate(attempts[:CONFIG.max_attempts]):
        provider, model, key = attempt["provider"], attempt["model"], attempt["key"]
        key_manager.reserve_key(provider, key)

        context.provider, context.model, context.attempt = provider.name, model, i
        timeout = timeout_manager.get(provider.name, model)

        try:
            payload = (
                build_openai_payload(model, messages, temperature, max_tokens)
                if provider.type == "openai"
                else build_gemini_payload(model, messages, temperature, max_tokens)
            )

            start = time.time()
            run_plugins("before_request", {"messages": messages})
            result = send_request(provider, model, key, payload, timeout)
            latency = time.time() - start

            metrics.update(provider.name, model, True, latency)
            health_engine.on_success(provider.name, key, model)
            timeout_manager.update(provider.name, model, latency, True)

            if CONFIG.cache_enabled:
                cache_set(cache_key, result)

            log_event("INFO", "success", request_id=context.request_id, provider=provider.name, model=model, latency=latency)
            run_plugins("after_response", {"response": result})
            return result

        except Exception as e:
            last_error = str(e) or e.__class__.__name__
            log_event("WARN", "failure", request_id=context.request_id, provider=provider.name, model=model, error=last_error)
            health_engine.on_failure(provider.name, key, model, last_error)
            metrics.update(provider.name, model, False, 0)
            timeout_manager.update(provider.name, model, 0, False)
            time.sleep(max(0, compute_backoff(i)))

    raise GatewayError(f"all_failed | {last_error or 'unknown_error'}")


# ============================================================
# RATE LIMITER
# ============================================================

class RateLimiter:

    def __init__(self, rate_per_sec=5, capacity=10):
        self.rate = rate_per_sec
        self.capacity = capacity
        self.tokens = capacity
        self.last = time.time()
        self.lock = threading.Lock()

    def acquire(self):
        with self.lock:
            now = time.time()
            delta = now - self.last
            self.tokens = min(self.capacity, self.tokens + delta * self.rate)
            self.last = now
            if self.tokens >= 1:
                self.tokens -= 1
                return True
            return False


rate_limiter = RateLimiter(rate_per_sec=10, capacity=20)


# ============================================================
# REQUEST COALESCING
# ============================================================

class InFlightRegistry:

    def __init__(self):
        self.futures: Dict[str, Any] = {}
        self.lock = threading.Lock()

    def get(self, key):
        with self.lock:
            return self.futures.get(key)

    def set(self, key, event):
        with self.lock:
            self.futures[key] = event

    def delete(self, key):
        with self.lock:
            self.futures.pop(key, None)


inflight = InFlightRegistry()
executor = ThreadPoolExecutor(max_workers=20)


def execute_safe(messages, temperature=0.7, max_tokens=None) -> str:
    cache_key = CACHE.make_key("auto", messages, {"temperature": temperature, "max_tokens": max_tokens})

    existing = inflight.get(cache_key)
    if existing:
        logger.info("[COALESCED REQUEST]")
        existing.wait()
        cached = CACHE.get(cache_key)
        if cached is not None:
            return cached
        # NOVO: se a requisição "líder" falhou, o coalescing antigo
        # retornava None silenciosamente pros seguidores (que aí quebravam
        # mais na frente com erro genérico). Agora refazemos a chamada em
        # vez de assumir sucesso.

    event = threading.Event()
    inflight.set(cache_key, event)

    try:
        while not rate_limiter.acquire():
            time.sleep(0.05)
        return execute(messages, temperature, max_tokens)
    finally:
        event.set()
        inflight.delete(cache_key)


def execute_async(messages, temperature=0.7, max_tokens=None):
    return executor.submit(execute_safe, messages, temperature, max_tokens)


def execute_batch(batch_messages: List[List[Dict[str, str]]]):
    futures = [execute_async(m) for m in batch_messages]
    results = []
    for f in futures:
        try:
            results.append(f.result())
        except Exception as e:
            results.append(str(e))
    return results


# ============================================================
# BACKPRESSURE
# ============================================================

class BackpressureController:

    def __init__(self, max_queue=100):
        self.queue_size = 0
        self.max_queue = max_queue
        self.lock = threading.Lock()

    def acquire(self):
        with self.lock:
            if self.queue_size >= self.max_queue:
                return False
            self.queue_size += 1
            return True

    def release(self):
        with self.lock:
            self.queue_size = max(0, self.queue_size - 1)


backpressure = BackpressureController()


def execute_protected(messages, temperature: float = 0.7, max_tokens: Optional[int] = None) -> str:
    if not backpressure.acquire():
        raise GatewayError("system_overloaded_backpressure")
    try:
        return execute_safe(messages, temperature, max_tokens)
    finally:
        backpressure.release()


def execute_stream(messages: List[Dict[str, str]]):
    result = execute_protected(messages)
    for i in range(0, len(result), 20):
        yield result[i:i + 20]


# ============================================================
# REDIS CACHE (OPCIONAL)
# ============================================================

REDIS_ENABLED = False
redis_client = None

try:
    import redis
    redis_client = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True, socket_connect_timeout=1)
    redis_client.ping()
    REDIS_ENABLED = True
    log_event("INFO", "redis_connected")
except Exception as e:
    REDIS_ENABLED = False
    redis_client = None
    log_event("WARN", "redis_disabled", error=str(e))


def cache_get(key):
    if REDIS_ENABLED and redis_client:
        try:
            val = redis_client.get(key)
            if val:
                return val
        except Exception as e:
            log_event("WARN", "redis_get_failed", error=str(e))
    return CACHE.get(key)


def cache_set(key, value):
    if REDIS_ENABLED and redis_client:
        try:
            redis_client.setex(key, CONFIG.cache_ttl, value)
        except Exception as e:
            log_event("WARN", "redis_set_failed", error=str(e))
    CACHE.set(key, value)


# ============================================================
# PRIORITY QUEUE
# ============================================================

import queue

task_queue = queue.PriorityQueue()
_priority_counter = itertools.count()


def submit_task(messages, priority=5, temperature=0.7, max_tokens=None) -> Future:
    future: Future = Future()
    tie_breaker = next(_priority_counter)
    task_queue.put((priority, tie_breaker, future, messages, temperature, max_tokens))
    return future


def worker():
    while True:
        priority, tie_breaker, future, messages, temperature, max_tokens = task_queue.get()
        if not future.set_running_or_notify_cancel():
            task_queue.task_done()
            continue
        try:
            result = execute_protected(messages, temperature, max_tokens)
            future.set_result(result)
        except Exception as e:
            log_event("WARN", "worker_task_failed", error=str(e))
            future.set_exception(e)
        finally:
            task_queue.task_done()


for _ in range(5):
    threading.Thread(target=worker, daemon=True).start()


# ============================================================
# PLUGINS
# ============================================================

PLUGINS = []


def register_plugin(func):
    PLUGINS.append(func)


def run_plugins(stage, data):
    for plugin in PLUGINS:
        try:
            plugin(stage, data)
        except Exception as e:
            log_event("WARN", "plugin_error", error=str(e))


# ============================================================
# HEALTH CHECK
# ============================================================

def health_status():
    status = {"providers": {}, "queue_size": task_queue.qsize(), "cache_size": len(CACHE.store)}
    for provider in PROVIDERS.values():
        ok = total = 0
        for model in provider.models:
            for key in provider.keys:
                if not key:
                    continue
                total += 1
                if health_engine.is_available(provider.name, key, model):
                    ok += 1
        status["providers"][provider.name] = {"healthy": ok, "total": total}
    return status


# ============================================================
# PERSISTENCE LOOP (NOVO)
# ============================================================

def _persist_all():
    try:
        metrics.persist()
        health_engine.persist()
        timeout_manager.persist()
    except Exception as e:
        log_event("WARN", "persist_all_failed", error=str(e))


def _persistence_loop():
    while True:
        time.sleep(CONFIG.persist_every_seconds)
        _persist_all()


threading.Thread(target=_persistence_loop, daemon=True).start()
atexit.register(_persist_all)


# ============================================================
# STANDALONE SERVER — ASGI APP NO NÍVEL DO MÓDULO (FIX DO BUG RAIZ)
# ============================================================
#
# ANTES: `app = FastAPI()` e os endpoints estavam dentro de
# `if __name__ == "__main__":`, então `uvicorn llm_gateway:app` (que só
# importa o módulo, nunca executa esse bloco) via um módulo sem nenhum
# atributo `app` — daí o "Attribute app not found", e o mesmo erro pra
# qualquer nome que se tentasse (`api`, `server`...).
#
# AGORA: tudo isso vive no nível do módulo. `uvicorn llm_gateway:app`
# funciona direto. Rodar este arquivo como serviço standalone é opcional
# — normalmente você só roda `router:app` (porta 8001), que importa as
# FUNÇÕES deste módulo (não o `app` dele) como biblioteca. Ter os dois
# processos rodando ao mesmo tempo (gateway isolado na 8000 + router na
# 8001) é seguro, útil pra depurar o gateway sem a camada de estratégias
# do router no meio.

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

app = FastAPI(
    title="LLM Gateway",
    version="3.0",
    description="Camada de provedores OpenAI-compatible (Groq / OpenRouter / Gemini) com failover, circuit breaker e cache.",
    docs_url="/docs",
    redoc_url=None,
)

if CONFIG.cors_origins:
    origins = ["*"] if CONFIG.cors_origins.strip() == "*" else [o.strip() for o in CONFIG.cors_origins.split(",")]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def build_openai_error(message: str, error_type: str = "invalid_request_error", code: Optional[str] = None):
    """Formato de erro OpenAI, consistente com o do router — clientes
    OpenAI-compatible sabem parsear `{"error": {...}}` melhor do que o
    `{"detail": ...}` padrão do FastAPI."""
    return {"error": {"message": message, "type": error_type, "code": code}}


def require_api_key(request: Request):
    """NOVO: auth opcional. Desligada por padrão (uso local/dev). Ligue
    com GATEWAY_REQUIRE_AUTH=true + GATEWAY_API_KEY=<sua-chave> se este
    gateway for exposto além de 127.0.0.1."""
    if not CONFIG.require_auth:
        return
    auth = request.headers.get("authorization", "")
    token = auth.split("Bearer ", 1)[-1] if auth.startswith("Bearer ") else ""
    if not CONFIG.api_key or token != CONFIG.api_key:
        raise HTTPException(status_code=401, detail="unauthorized")


class ChatMessage(BaseModel):
    role: str
    content: str

    @field_validator("role")
    @classmethod
    def validate_role(cls, v):
        # Nunca derruba a request inteira por causa de um role fora do
        # enum esperado — normaliza, como o router já faz.
        if v not in ("system", "user", "assistant"):
            return "user"
        return v


class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    priority: int = Field(default=5, ge=1, le=10)
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    stream: bool = False

    @field_validator("messages")
    @classmethod
    def not_empty(cls, v):
        if not v:
            raise ValueError("messages não pode ser vazio")
        return v

    # Sem Field(ge=.., le=..) em temperature/max_tokens de propósito: ver
    # nota extensa no router.py sobre por que constraints do Pydantic
    # geram 422 "cru" em vez de clampar. Aqui clampamos manualmente.
    @field_validator("temperature", mode="after")
    @classmethod
    def clamp_temperature(cls, v):
        if v is None:
            return 0.7
        return max(0.0, min(float(v), 2.0))

    @field_validator("max_tokens", mode="after")
    @classmethod
    def clamp_max_tokens(cls, v):
        if v is None or v <= 0:
            return None
        return min(int(v), CONFIG.max_tokens_hard_cap)


def _messages_to_dicts(messages: List[ChatMessage]) -> List[Dict[str, str]]:
    return [m.model_dump() for m in messages]


# --------------------------------------------------------------
# Endpoints "simples" (formato próprio, compatível com o router)
# --------------------------------------------------------------

@app.post("/chat", dependencies=[Depends(require_api_key)])
def chat(req: ChatRequest):
    try:
        payload_messages = _messages_to_dicts(req.messages)
        future = submit_task(payload_messages, priority=req.priority, temperature=req.temperature, max_tokens=req.max_tokens)
        result = future.result(timeout=CONFIG.timeout * CONFIG.max_attempts + 30)
        return {"response": result}
    except NoProvidersAvailableError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# --------------------------------------------------------------
# Endpoint OpenAI-compat direto no gateway (sem a camada de
# estratégias do router) — útil pra testar o gateway isolado.
# --------------------------------------------------------------

@app.post("/v1/chat/completions", dependencies=[Depends(require_api_key)])
def openai_chat_completions(req: ChatRequest):
    request_id = new_request_id()
    try:
        payload_messages = _messages_to_dicts(req.messages)
        result_text = execute_protected(payload_messages, temperature=req.temperature, max_tokens=req.max_tokens)
    except NoProvidersAvailableError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    completion_tokens = len(result_text.split())
    return {
        "id": f"chatcmpl-{request_id}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "gateway",
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": result_text},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": completion_tokens, "total_tokens": completion_tokens},
    }


_MODEL_INFO = {"id": "gateway", "object": "model", "owned_by": "local", "created": int(time.time())}


@app.get("/v1/models")
def list_models():
    return {"object": "list", "data": [_MODEL_INFO]}


@app.get("/health")
def health_endpoint():
    return health_status()


@app.get("/stats")
def stats_endpoint():
    return {
        "metrics": metrics.snapshot(),
        "timeouts": timeout_manager.snapshot(),
        "queue_size": task_queue.qsize(),
        "cache_size": len(CACHE.store),
        "redis_enabled": REDIS_ENABLED,
        "config": {
            "max_tokens_hard_cap": CONFIG.max_tokens_hard_cap,
            "require_auth": CONFIG.require_auth,
            "timeout": CONFIG.timeout,
            "max_attempts": CONFIG.max_attempts,
        },
    }


@app.get("/")
def root():
    return {"service": "llm-gateway", "status": "ok", "version": "3.0"}


# --------------------------------------------------------------
# Exception handlers globais (formato OpenAI, igual ao router)
# --------------------------------------------------------------

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    log_event("WARN", "validation_error", path=str(request.url.path), errors=str(exc.errors()))
    return JSONResponse(
        status_code=400,
        content=build_openai_error(f"Requisição inválida: {exc.errors()}", code="validation_error"),
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    log_event("ERROR", "unhandled_error", path=str(request.url.path), error=str(exc))
    return JSONResponse(
        status_code=500,
        content=build_openai_error("internal_error", error_type="server_error", code="internal_error"),
    )


# --------------------------------------------------------------
# Startup / shutdown hooks
# --------------------------------------------------------------

@app.on_event("startup")
async def on_startup():
    log_event(
        "INFO", "gateway_startup",
        total_keys=_total_keys,
        max_tokens_hard_cap=CONFIG.max_tokens_hard_cap,
        require_auth=CONFIG.require_auth,
        redis_enabled=REDIS_ENABLED,
    )


@app.on_event("shutdown")
async def on_shutdown():
    # Flush garantido além do atexit (nem sempre atexit roda em todo
    # cenário de shutdown do Uvicorn com --reload).
    _persist_all()
    log_event("INFO", "gateway_shutdown")


# ============================================================
# EXECUÇÃO DIRETA (python llm_gateway.py) — OPCIONAL
# ============================================================
#
# Uso normal é `uvicorn llm_gateway:app --port 8000`. Este bloco só
# existe pra permitir `python llm_gateway.py` também funcionar, lendo
# host/porta de env vars pra não ficar hardcoded.

if __name__ == "__main__":
    import uvicorn

    host = os.getenv("GATEWAY_HOST", "127.0.0.1")
    port = int(os.getenv("GATEWAY_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
