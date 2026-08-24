import os
import time
import json
import random
import hashlib
import logging
import itertools
import threading
import atexit
import uuid

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
    payload = {
        "time": time.time(),
        "level": level,
        "msg": message,
        **kwargs,
    }
    print(json.dumps(payload, ensure_ascii=False))


def new_request_id():
    return str(uuid.uuid4())


# ============================================================
# GLOBAL CONFIG
# ============================================================

@dataclass
class GatewayConfig:
    timeout: int = int(os.getenv("GATEWAY_TIMEOUT", "60"))
    max_attempts: int = int(os.getenv("GATEWAY_MAX_ATTEMPTS", "10"))

    cache_enabled: bool = os.getenv("GATEWAY_CACHE_ENABLED", "true").lower() == "true"
    cache_ttl: int = int(os.getenv("GATEWAY_CACHE_TTL", "600"))

    failure_threshold: int = int(os.getenv("GATEWAY_FAILURE_THRESHOLD", "3"))
    cooldown_seconds: int = int(os.getenv("GATEWAY_COOLDOWN_SECONDS", "60"))

    max_retry_delay: int = int(os.getenv("GATEWAY_MAX_RETRY_DELAY", "20"))

    state_dir: str = os.getenv(
        "GATEWAY_STATE_DIR",
        "./.gateway_state",
    )

    persist_every_seconds: int = int(
        os.getenv("GATEWAY_PERSIST_EVERY", "20")
    )

    max_tracked_entries: int = int(
        os.getenv("GATEWAY_MAX_TRACKED_ENTRIES", "500")
    )

    # Teto absoluto da saída gerada.
    # IMPORTANTE:
    # Não usamos 8192 automaticamente, porque Groq contabiliza
    # input + output no TPM.
    max_tokens_hard_cap: int = int(
        os.getenv("GATEWAY_MAX_TOKENS_CAP", "4096")
    )

    # Orçamento conservador para Groq.
    # Serve para reduzir 413 causados por TPM.
    groq_tpm_budget: int = int(
        os.getenv("GROQ_TPM_BUDGET", "7500")
    )

    # Margem de segurança do orçamento.
    groq_tpm_safety_margin: int = int(
        os.getenv("GROQ_TPM_SAFETY_MARGIN", "500")
    )

    require_auth: bool = (
        os.getenv("GATEWAY_REQUIRE_AUTH", "false").lower() == "true"
    )

    api_key: str = os.getenv("GATEWAY_API_KEY", "")

    cors_origins: str = os.getenv(
        "GATEWAY_CORS_ORIGINS",
        "",
    )


CONFIG = GatewayConfig()

os.makedirs(CONFIG.state_dir, exist_ok=True)


# ============================================================
# PROVIDERS
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
        name="groq",
        priority=1,
        type="openai",
        url="https://api.groq.com/openai/v1/chat/completions",
        keys=[
            os.getenv("GROQ_KEY_1"),
            os.getenv("GROQ_KEY_2"),
            os.getenv("GROQ_KEY_3"),
        ],
        models=[
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
            "qwen/qwen3.6-27b",
            "meta-llama/llama-4-scout-17b-16e-instruct",
            "groq/compound",
            "groq/compound-mini",
        ],
    ),

    "openrouter": ProviderConfig(
        name="openrouter",
        priority=2,
        type="openai",
        url="https://openrouter.ai/api/v1/chat/completions",
        keys=[
            os.getenv("OPENROUTER_KEY_1"),
            os.getenv("OPENROUTER_KEY_2"),
            os.getenv("OPENROUTER_KEY_3"),
        ],
        models=[
            "nvidia/nemotron-3-super-120b-a12b:free",
            "nvidia/nemotron-3-ultra-550b-a55b:free",
            "google/gemma-4-31b-it:free",
            "google/gemma-4-26b-a4b-it:free",
            "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
            "nvidia/nemotron-3.5-lightning:free",
            "liquid/lfm-2.5-2.6b:free",
],
    ),

    "gemini": ProviderConfig(
        name="gemini",
        priority=3,
        type="gemini",
        url="https://generativelanguage.googleapis.com/v1beta/models",
        keys=[
            os.getenv("GEMINI_KEY_1"),
            os.getenv("GEMINI_KEY_2"),
        ],
        models=[
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
            "gemini-2.0-flash",
        ],
    ),
}


_total_keys = sum(
    1
    for provider in PROVIDERS.values()
    for key in provider.keys
    if key
)

if _total_keys == 0:
    log_event(
        "WARN",
        "no_provider_keys_configured",
        detail="Nenhuma API key configurada.",
    )
else:
    log_event(
        "INFO",
        "providers_loaded",
        total_keys=_total_keys,
    )


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
# PERSISTENT JSON
# ============================================================

class PersistentJSON:

    def __init__(self, path: str):
        self.path = path
        self.lock = threading.Lock()

    def load(self, default):
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return default

    def save(self, data):
        tmp = self.path + ".tmp"

        try:
            with self.lock:
                with open(tmp, "w", encoding="utf-8") as fh:
                    json.dump(
                        data,
                        fh,
                        ensure_ascii=False,
                    )

                os.replace(tmp, self.path)

        except Exception as exc:
            log_event(
                "WARN",
                "persist_failed",
                path=self.path,
                error=str(exc),
            )


_metrics_store = PersistentJSON(
    os.path.join(CONFIG.state_dir, "metrics.json")
)

_health_store = PersistentJSON(
    os.path.join(CONFIG.state_dir, "health.json")
)

_timeouts_store = PersistentJSON(
    os.path.join(CONFIG.state_dir, "timeouts.json")
)


# ============================================================
# CACHE
# ============================================================

class SmartCache:

    def __init__(self):
        self.store = {}
        self.lock = threading.Lock()

    def make_key(self, model, messages, extra=None):
        raw = json.dumps(
            {
                "model": model,
                "messages": messages,
                "extra": extra or {},
            },
            sort_keys=True,
            ensure_ascii=False,
        )

        return hashlib.sha256(
            raw.encode("utf-8")
        ).hexdigest()

    def get(self, key):
        with self.lock:
            item = self.store.get(key)

            if not item:
                return None

            if time.time() - item["time"] > CONFIG.cache_ttl:
                self.store.pop(key, None)
                return None

            return item["value"]

    def set(self, key, value):
        with self.lock:
            self.store[key] = {
                "value": value,
                "time": time.time(),
            }


CACHE = SmartCache()


# ============================================================
# METRICS
# ============================================================

class Metrics:

    def __init__(self):
        raw = _metrics_store.load({})

        self.data = defaultdict(
            lambda: {
                "success": 1,
                "fail": 1,
                "latency": 1.0,
            }
        )

        for key, value in raw.items():
            parts = key.split("::", 1)

            if len(parts) == 2:
                self.data[
                    (parts[0], parts[1])
                ] = value

    def update(
        self,
        provider,
        model,
        success,
        latency,
    ):
        item = self.data[(provider, model)]

        if success:
            item["success"] += 1
        else:
            item["fail"] += 1

        if latency > 0:
            item["latency"] = (
                item["latency"] + latency
            ) / 2

        self._prune()

    def score(self, provider, model):
        item = self.data[(provider, model)]

        total = (
            item["success"] +
            item["fail"]
        )

        success_rate = (
            item["success"] / max(total, 1)
        )

        latency = max(
            item["latency"],
            0.1,
        )

        return (
            success_rate * 10
        ) / latency

    def _prune(self):
        if len(self.data) <= CONFIG.max_tracked_entries:
            return

        worst = sorted(
            self.data.items(),
            key=lambda pair: (
                pair[1]["success"],
                -pair[1]["fail"],
            ),
        )[:50]

        for key, _ in worst:
            self.data.pop(key, None)

    def snapshot(self):
        return {
            f"{provider}:{model}": value
            for (provider, model), value
            in self.data.items()
        }

    def persist(self):
        _metrics_store.save(
            {
                f"{provider}::{model}": value
                for (provider, model), value
                in self.data.items()
            }
        )


metrics = Metrics()


# ============================================================
# CIRCUIT BREAKER
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

    # Diferentes tipos de falha.
    model_errors: int = 0
    rate_limits: int = 0
    payload_errors: int = 0


class HealthEngine:

    def __init__(self):
        self.states: Dict[str, HealthState] = {}
        self.lock = threading.Lock()

        raw = _health_store.load({})

        for key, value in raw.items():
            try:
                self.states[key] = HealthState(
                    **value
                )
            except Exception:
                self.states[key] = HealthState()

    def _key(
        self,
        provider,
        api_key,
        model,
    ):
        masked = (
            (api_key or "")[:6]
        )

        return (
            f"{provider}:{masked}:{model}"
        )

    def _get(self, key):
        if key not in self.states:
            self.states[key] = HealthState()

        return self.states[key]

    def is_available(
        self,
        provider,
        api_key,
        model,
    ):
        key = self._key(
            provider,
            api_key,
            model,
        )

        with self.lock:
            state = self._get(key)

            now = time.time()

            if state.state == CircuitState.OPEN:

                if now >= state.cooldown_until:
                    state.state = (
                        CircuitState.HALF_OPEN
                    )

                    logger.info(
                        "[RECOVERY] %s -> HALF_OPEN",
                        key,
                    )

                    return True

                return False

            return True

    def on_failure(
        self,
        provider,
        api_key,
        model,
        error,
        failure_kind="generic",
    ):
        key = self._key(
            provider,
            api_key,
            model,
        )

        with self.lock:
            state = self._get(key)

            state.failures += 1
            state.last_failure = time.time()
            state.success_streak = 0

            if failure_kind == "model_not_found":
                state.model_errors += 1

                # Modelo inexistente não precisa esperar dezenas
                # de tentativas para ser considerado indisponível.
                state.cooldown_until = (
                    time.time() + 3600
                )
                state.state = CircuitState.OPEN

                return

            if failure_kind == "rate_limit":
                state.rate_limits += 1

                # Rate limit: cooldown maior.
                penalty = min(
                    300,
                    max(
                        CONFIG.cooldown_seconds * 2,
                        90,
                    ),
                )

            elif failure_kind == "payload":
                state.payload_errors += 1

                # Payload grande: não vale insistir
                # imediatamente com o mesmo modelo/key.
                penalty = 180

            else:
                penalty = min(
                    300,
                    CONFIG.cooldown_seconds
                    * state.failures,
                )

            jitter = random.uniform(
                0,
                penalty * 0.15,
            )

            penalty += jitter

            state.cooldown_until = (
                time.time() + penalty
            )

            if state.failures >= CONFIG.failure_threshold:
                state.state = CircuitState.OPEN

                logger.warning(
                    "[CIRCUIT OPEN] %s | kind=%s | penalty=%.1fs",
                    key,
                    failure_kind,
                    penalty,
                )

    def on_success(
        self,
        provider,
        api_key,
        model,
    ):
        key = self._key(
            provider,
            api_key,
            model,
        )

        with self.lock:
            state = self._get(key)

            state.success_streak += 1
            state.failures = 0

            if state.state == CircuitState.HALF_OPEN:
                if state.success_streak >= 2:
                    state.state = (
                        CircuitState.CLOSED
                    )

                    logger.info(
                        "[CIRCUIT CLOSED] %s",
                        key,
                    )

    def health_score(
        self,
        provider,
        api_key,
        model,
    ):
        key = self._key(
            provider,
            api_key,
            model,
        )

        state = self._get(key)

        if state.state == CircuitState.OPEN:
            return 0

        penalty = (
            1 +
            state.failures +
            state.rate_limits * 2 +
            state.payload_errors
        )

        bonus = (
            1 +
            state.success_streak
        )

        return bonus / penalty

    def persist(self):
        with self.lock:
            _health_store.save(
                {
                    key: vars(value)
                    for key, value
                    in self.states.items()
                }
            )


health_engine = HealthEngine()


# ============================================================
# KEY MANAGER
# ============================================================

class KeyManager:

    def __init__(self):
        self.usage = defaultdict(int)
        self.lock = threading.Lock()

    def _valid_keys(
        self,
        provider: ProviderConfig,
        model: str,
    ):
        return [
            key
            for key in provider.keys
            if key
            and health_engine.is_available(
                provider.name,
                key,
                model,
            )
        ]

    def _best_key(
        self,
        provider: ProviderConfig,
        model: str,
    ):
        keys = self._valid_keys(
            provider,
            model,
        )

        if not keys:
            return None

        with self.lock:
            scored = []

            for key in keys:
                score = (
                    health_engine.health_score(
                        provider.name,
                        key,
                        model,
                    )
                    -
                    (
                        self.usage[
                            (provider.name, key)
                        ] * 0.01
                    )
                )

                scored.append(
                    (key, score)
                )

        scored.sort(
            key=lambda item: -item[1]
        )

        return scored[0][0]

    def peek_key(
        self,
        provider,
        model,
    ):
        return self._best_key(
            provider,
            model,
        )

    def reserve_key(
        self,
        provider,
        key,
    ):
        with self.lock:
            self.usage[
                (provider.name, key)
            ] += 1

    def pick_key(
        self,
        provider,
        model,
    ):
        key = self.peek_key(
            provider,
            model,
        )

        if key:
            self.reserve_key(
                provider,
                key,
            )

        return key


key_manager = KeyManager()


# ============================================================
# ERRORS
# ============================================================

class GatewayError(Exception):
    pass


class RateLimitError(GatewayError):
    pass


class ModelNotFoundError(GatewayError):
    pass


class PayloadTooLargeError(GatewayError):
    pass


class ProviderError(GatewayError):
    pass


class GatewayTimeoutError(GatewayError):
    pass


class EmptyResponseError(GatewayError):
    pass


class NoProvidersAvailableError(GatewayError):
    pass


# ============================================================
# ATTEMPT RANKING
# ============================================================

def rank_attempts():
    attempts = []

    for provider in PROVIDERS.values():

        for model in provider.models:

            key = key_manager.peek_key(
                provider,
                model,
            )

            if not key:
                continue

            score = (
                provider.priority * -1
                +
                metrics.score(
                    provider.name,
                    model,
                )
                +
                health_engine.health_score(
                    provider.name,
                    key,
                    model,
                )
            )

            attempts.append(
                {
                    "provider": provider,
                    "model": model,
                    "key": key,
                    "score": score,
                }
            )

    attempts.sort(
        key=lambda item: -item["score"]
    )

    return attempts


# ============================================================
# TIMEOUT MANAGER
# ============================================================

class TimeoutManager:

    def __init__(self):
        self.base = CONFIG.timeout

        raw = _timeouts_store.load({})

        self.history = defaultdict(
            lambda: self.base
        )

        for key, value in raw.items():
            parts = key.split("::", 1)

            if len(parts) == 2:
                self.history[
                    (parts[0], parts[1])
                ] = value

    def get(
        self,
        provider,
        model,
    ):
        return min(
            max(
                5,
                self.history[
                    (provider, model)
                ],
            ),
            120,
        )

    def update(
        self,
        provider,
        model,
        latency,
        success,
    ):
        key = (provider, model)
        current = self.history[key]

        if success:
            self.history[key] = (
                current + latency
            ) / 2
        else:
            self.history[key] = min(
                120,
                current * 1.5,
            )

    def snapshot(self):
        return {
            f"{provider}:{model}": value
            for (provider, model), value
            in self.history.items()
        }

    def persist(self):
        _timeouts_store.save(
            {
                f"{provider}::{model}": value
                for (provider, model), value
                in self.history.items()
            }
        )


timeout_manager = TimeoutManager()


# ============================================================
# BACKOFF
# ============================================================

def compute_backoff(attempt):
    base = 0.5

    delay = min(
        CONFIG.max_retry_delay,
        base * (2 ** attempt),
    )

    jitter = delay * 0.2

    return delay + random.uniform(
        -jitter,
        jitter,
    )


# ============================================================
# TOKEN / SIZE ESTIMATION
# ============================================================

def estimate_tokens(messages):
    """
    Estimativa conservadora.

    Não é tokenizer oficial do provider.
    Serve apenas para evitar requests claramente grandes.
    """
    text = ""

    for message in messages:
        content = message.get(
            "content",
            "",
        )

        if content:
            text += str(content)
            text += "\n"

    # Aproximação: ~4 caracteres/token.
    estimated = max(
        1,
        len(text) // 4,
    )

    return estimated


def calculate_output_budget(
    provider,
    model,
    messages,
    requested_max_tokens,
):
    requested = requested_max_tokens

    if requested is None:
        requested = CONFIG.max_tokens_hard_cap

    requested = max(
        256,
        int(requested),
    )

    requested = min(
        requested,
        CONFIG.max_tokens_hard_cap,
    )

    estimated_input = estimate_tokens(
        messages
    )

    if provider.name == "groq":
        usable_budget = max(
            1024,
            CONFIG.groq_tpm_budget
            - CONFIG.groq_tpm_safety_margin,
        )

        remaining = (
            usable_budget
            - estimated_input
        )

        # Nunca pedimos mais saída do que o
        # orçamento estimado permite.
        requested = min(
            requested,
            max(256, remaining),
        )

    return max(
        256,
        requested,
    )


# ============================================================
# RESPONSE PARSERS
# ============================================================

def safe_extract_text(data):

    try:
        value = data[
            "choices"
        ][0][
            "message"
        ][
            "content"
        ]

        if isinstance(value, str):
            return value

    except Exception:
        pass

    try:
        value = data[
            "candidates"
        ][0][
            "content"
        ][
            "parts"
        ][0][
            "text"
        ]

        if isinstance(value, str):
            return value

    except Exception:
        pass

    return ""


def build_openai_payload(
    model,
    messages,
    temperature=0.7,
    max_tokens=None,
):
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }

    if max_tokens is not None:
        payload[
            "max_tokens"
        ] = max_tokens

    return payload


def build_gemini_payload(
    model,
    messages,
    temperature=0.7,
    max_tokens=None,
):
    role_map = {
        "user": "user",
        "assistant": "model",
        "model": "model",
    }

    contents = []
    system_parts = []

    for message in messages:
        role = message.get(
            "role",
            "user",
        )

        content = message.get(
            "content",
            "",
        )

        if role == "system":
            system_parts.append(
                content
            )
            continue

        contents.append(
            {
                "role": role_map.get(
                    role,
                    "user",
                ),
                "parts": [
                    {
                        "text": content
                    }
                ],
            }
        )

    generation_config = {
        "temperature": temperature,
    }

    if max_tokens is not None:
        generation_config[
            "maxOutputTokens"
        ] = max_tokens

    payload = {
        "contents": contents,
        "generationConfig": generation_config,
    }

    if system_parts:
        payload[
            "systemInstruction"
        ] = {
            "parts": [
                {
                    "text": "\n".join(
                        system_parts
                    )
                }
            ]
        }

    return payload


# ============================================================
# HTTP SESSION
# ============================================================

session = requests.Session()

session.headers.update(
    {
        "Content-Type": "application/json",
        "User-Agent": "automa-o-llm-gateway/4.0",
    }
)


# ============================================================
# HTTP CLIENT
# ============================================================

def send_request(
    provider: ProviderConfig,
    model,
    key,
    payload,
    timeout,
):
    headers = {
        "Content-Type": "application/json",
    }

    if provider.type == "openai":
        headers[
            "Authorization"
        ] = f"Bearer {key}"

    url = provider.url

    if provider.type == "gemini":
        url = (
            f"{provider.url}/"
            f"{model}:generateContent"
            f"?key={key}"
        )

    for attempt in range(2):

        try:
            response = session.post(
                url,
                headers=headers,
                json=payload,
                timeout=timeout,
            )

            status = response.status_code

            if status == 429:
                retry_after = (
                    response.headers.get(
                        "retry-after",
                        "",
                    )
                )

                raise RateLimitError(
                    f"http_429 retry_after={retry_after}"
                )

            if status == 413:
                raise PayloadTooLargeError(
                    "http_413: "
                    + response.text[:400]
                )

            if status == 404:
                raise ModelNotFoundError(
                    "http_404: "
                    + response.text[:400]
                )

            if status >= 500:
                raise ProviderError(
                    f"http_{status}"
                )

            if status >= 400:
                raise ProviderError(
                    f"http_{status}: "
                    f"{response.text[:400]}"
                )

            try:
                data = response.json()
            except ValueError as exc:
                raise ProviderError(
                    f"invalid_json_response: {exc}"
                ) from exc

            text = safe_extract_text(
                data
            )

            if not text or not text.strip():
                raise EmptyResponseError(
                    "empty_response"
                )

            return text

        except (
            RateLimitError,
            ModelNotFoundError,
            PayloadTooLargeError,
            ProviderError,
            EmptyResponseError,
        ):
            raise

        except requests.Timeout as exc:
            if attempt == 1:
                raise GatewayTimeoutError(
                    str(exc)
                ) from exc

        except requests.RequestException as exc:
            if attempt == 1:
                raise ProviderError(
                    str(exc)
                ) from exc

    raise ProviderError(
        "send_request_exhausted_retries"
    )


# ============================================================
# ERROR CLASSIFICATION
# ============================================================

def classify_failure(error):
    if isinstance(
        error,
        ModelNotFoundError,
    ):
        return "model_not_found"

    if isinstance(
        error,
        RateLimitError,
    ):
        return "rate_limit"

    if isinstance(
        error,
        PayloadTooLargeError,
    ):
        return "payload"

    if isinstance(
        error,
        GatewayTimeoutError,
    ):
        return "timeout"

    if isinstance(
        error,
        EmptyResponseError,
    ):
        return "empty_response"

    return "generic"


# ============================================================
# CORE EXECUTION
# ============================================================

def execute(
    messages: List[Dict[str, str]],
    temperature: float = 0.7,
    max_tokens: Optional[int] = None,
) -> str:

    context = RequestContext(
        request_id=new_request_id(),
        start_time=time.time(),
    )

    if not messages:
        raise GatewayError(
            "messages_empty"
        )

    cache_key = CACHE.make_key(
        "auto",
        messages,
        {
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
    )

    if CONFIG.cache_enabled:
        cached = cache_get(
            cache_key
        )

        if cached is not None:
            log_event(
                "INFO",
                "cache_hit",
                request_id=context.request_id,
            )

            return cached

    attempts = rank_attempts()

    if not attempts:
        raise NoProvidersAvailableError(
            "Nenhum provider disponível."
        )

    last_error = None

    attempted_models = set()

    for index, attempt in enumerate(
        attempts[:CONFIG.max_attempts]
    ):

        provider = attempt[
            "provider"
        ]

        model = attempt["model"]
        key = attempt["key"]

        pair = (
            provider.name,
            model,
        )

        if pair in attempted_models:
            continue

        attempted_models.add(pair)

        context.provider = (
            provider.name
        )
        context.model = model
        context.attempt = index

        output_budget = (
            calculate_output_budget(
                provider,
                model,
                messages,
                max_tokens,
            )
        )

        timeout = timeout_manager.get(
            provider.name,
            model,
        )

        try:

            payload = (
                build_openai_payload(
                    model,
                    messages,
                    temperature,
                    output_budget,
                )
                if provider.type == "openai"
                else
                build_gemini_payload(
                    model,
                    messages,
                    temperature,
                    output_budget,
                )
            )

            estimated_input = (
                estimate_tokens(
                    messages
                )
            )

            log_event(
                "INFO",
                "attempt",
                request_id=context.request_id,
                provider=provider.name,
                model=model,
                attempt=index,
                estimated_input_tokens=estimated_input,
                output_budget=output_budget,
            )

            start = time.time()

            run_plugins(
                "before_request",
                {
                    "messages": messages,
                    "provider": provider.name,
                    "model": model,
                },
            )

            result = send_request(
                provider,
                model,
                key,
                payload,
                timeout,
            )

            latency = (
                time.time() - start
            )

            metrics.update(
                provider.name,
                model,
                True,
                latency,
            )

            health_engine.on_success(
                provider.name,
                key,
                model,
            )

            timeout_manager.update(
                provider.name,
                model,
                latency,
                True,
            )

            if CONFIG.cache_enabled:
                cache_set(
                    cache_key,
                    result,
                )

            log_event(
                "INFO",
                "success",
                request_id=context.request_id,
                provider=provider.name,
                model=model,
                latency=latency,
            )

            run_plugins(
                "after_response",
                {
                    "response": result,
                    "provider": provider.name,
                    "model": model,
                },
            )

            return result

        except Exception as exc:

            last_error = (
                str(exc)
                or exc.__class__.__name__
            )

            failure_kind = (
                classify_failure(
                    exc
                )
            )

            log_event(
                "WARN",
                "failure",
                request_id=context.request_id,
                provider=provider.name,
                model=model,
                kind=failure_kind,
                error=last_error,
            )

            health_engine.on_failure(
                provider.name,
                key,
                model,
                last_error,
                failure_kind,
            )

            metrics.update(
                provider.name,
                model,
                False,
                0,
            )

            timeout_manager.update(
                provider.name,
                model,
                0,
                False,
            )

            # Modelo inexistente:
            # não desperdiçar tentativas.
            if failure_kind == "model_not_found":
                continue

            # Payload excessivo:
            # não repetir o MESMO modelo imediatamente.
            if failure_kind == "payload":
                continue

            # Rate limit:
            # pular para o próximo provider/model.
            if failure_kind == "rate_limit":
                continue

            time.sleep(
                max(
                    0,
                    compute_backoff(index),
                )
            )

    raise GatewayError(
        f"all_failed | "
        f"{last_error or 'unknown_error'}"
    )


# ============================================================
# RATE LIMITER
# ============================================================

class RateLimiter:

    def __init__(
        self,
        rate_per_sec=5,
        capacity=10,
    ):
        self.rate = rate_per_sec
        self.capacity = capacity
        self.tokens = capacity
        self.last = time.time()
        self.lock = threading.Lock()

    def acquire(self):

        with self.lock:

            now = time.time()

            delta = (
                now - self.last
            )

            self.tokens = min(
                self.capacity,
                self.tokens
                + delta * self.rate,
            )

            self.last = now

            if self.tokens >= 1:
                self.tokens -= 1
                return True

            return False


rate_limiter = RateLimiter(
    rate_per_sec=10,
    capacity=20,
)


# ============================================================
# REQUEST COALESCING
# ============================================================

class InFlightRegistry:

    def __init__(self):
        self.futures: Dict[
            str, threading.Event
        ] = {}

        self.lock = threading.Lock()

    def get(self, key):
        with self.lock:
            return self.futures.get(key)

    def set(self, key, event):
        with self.lock:
            self.futures[key] = event

    def delete(self, key):
        with self.lock:
            self.futures.pop(
                key,
                None,
            )


inflight = InFlightRegistry()

executor = ThreadPoolExecutor(
    max_workers=20
)


def execute_safe(
    messages,
    temperature=0.7,
    max_tokens=None,
):

    cache_key = CACHE.make_key(
        "auto",
        messages,
        {
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
    )

    existing = inflight.get(
        cache_key
    )

    if existing:

        logger.info(
            "[COALESCED REQUEST]"
        )

        existing.wait()

        cached = CACHE.get(
            cache_key
        )

        if cached is not None:
            return cached

    event = threading.Event()

    inflight.set(
        cache_key,
        event,
    )

    try:

        while not rate_limiter.acquire():
            time.sleep(0.05)

        return execute(
            messages,
            temperature,
            max_tokens,
        )

    finally:

        event.set()

        inflight.delete(
            cache_key
        )


def execute_async(
    messages,
    temperature=0.7,
    max_tokens=None,
):
    return executor.submit(
        execute_safe,
        messages,
        temperature,
        max_tokens,
    )


def execute_batch(
    batch_messages,
):
    futures = [
        execute_async(
            messages
        )
        for messages in batch_messages
    ]

    results = []

    for future in futures:

        try:
            results.append(
                future.result()
            )

        except Exception as exc:
            results.append(
                str(exc)
            )

    return results


# ============================================================
# BACKPRESSURE
# ============================================================

class BackpressureController:

    def __init__(
        self,
        max_queue=100,
    ):
        self.queue_size = 0
        self.max_queue = max_queue
        self.lock = threading.Lock()

    def acquire(self):

        with self.lock:

            if (
                self.queue_size
                >= self.max_queue
            ):
                return False

            self.queue_size += 1

            return True

    def release(self):

        with self.lock:

            self.queue_size = max(
                0,
                self.queue_size - 1,
            )


backpressure = (
    BackpressureController()
)


def execute_protected(
    messages,
    temperature=0.7,
    max_tokens=None,
):

    if not backpressure.acquire():
        raise GatewayError(
            "system_overloaded_backpressure"
        )

    try:
        return execute_safe(
            messages,
            temperature,
            max_tokens,
        )
    finally:
        backpressure.release()


def execute_stream(messages):
    result = execute_protected(
        messages
    )

    for index in range(
        0,
        len(result),
        20,
    ):
        yield result[
            index:index + 20
        ]


# ============================================================
# REDIS
# ============================================================

REDIS_ENABLED = False
redis_client = None

try:

    import redis

    redis_client = redis.Redis(
        host=os.getenv(
            "REDIS_HOST",
            "localhost",
        ),
        port=int(
            os.getenv(
                "REDIS_PORT",
                "6379",
            )
        ),
        db=0,
        decode_responses=True,
        socket_connect_timeout=1,
    )

    redis_client.ping()

    REDIS_ENABLED = True

    log_event(
        "INFO",
        "redis_connected",
    )

except Exception as exc:

    REDIS_ENABLED = False
    redis_client = None

    log_event(
        "WARN",
        "redis_disabled",
        error=str(exc),
    )


def cache_get(key):

    if (
        REDIS_ENABLED
        and redis_client
    ):

        try:

            value = redis_client.get(
                key
            )

            if value:
                return value

        except Exception as exc:

            log_event(
                "WARN",
                "redis_get_failed",
                error=str(exc),
            )

    return CACHE.get(key)


def cache_set(
    key,
    value,
):

    if (
        REDIS_ENABLED
        and redis_client
    ):

        try:

            redis_client.setex(
                key,
                CONFIG.cache_ttl,
                value,
            )

        except Exception as exc:

            log_event(
                "WARN",
                "redis_set_failed",
                error=str(exc),
            )

    CACHE.set(
        key,
        value,
    )


# ============================================================
# PRIORITY QUEUE
# ============================================================

import queue

task_queue = queue.PriorityQueue()

_priority_counter = itertools.count()


def submit_task(
    messages,
    priority=5,
    temperature=0.7,
    max_tokens=None,
):

    future: Future = Future()

    tie_breaker = next(
        _priority_counter
    )

    task_queue.put(
        (
            priority,
            tie_breaker,
            future,
            messages,
            temperature,
            max_tokens,
        )
    )

    return future


def worker():

    while True:

        (
            priority,
            tie_breaker,
            future,
            messages,
            temperature,
            max_tokens,
        ) = task_queue.get()

        if not future.set_running_or_notify_cancel():

            task_queue.task_done()

            continue

        try:

            result = execute_protected(
                messages,
                temperature,
                max_tokens,
            )

            future.set_result(
                result
            )

        except Exception as exc:

            log_event(
                "WARN",
                "worker_task_failed",
                error=str(exc),
            )

            future.set_exception(
                exc
            )

        finally:

            task_queue.task_done()


for _ in range(5):

    threading.Thread(
        target=worker,
        daemon=True,
    ).start()


# ============================================================
# PLUGINS
# ============================================================

PLUGINS = []


def register_plugin(func):
    PLUGINS.append(func)


def run_plugins(
    stage,
    data,
):

    for plugin in PLUGINS:

        try:

            plugin(
                stage,
                data,
            )

        except Exception as exc:

            log_event(
                "WARN",
                "plugin_error",
                error=str(exc),
            )


# ============================================================
# HEALTH
# ============================================================

def health_status():

    status = {
        "providers": {},
        "queue_size": task_queue.qsize(),
        "cache_size": len(
            CACHE.store
        ),
    }

    for provider in PROVIDERS.values():

        healthy = 0
        total = 0

        for model in provider.models:

            for key in provider.keys:

                if not key:
                    continue

                total += 1

                if health_engine.is_available(
                    provider.name,
                    key,
                    model,
                ):
                    healthy += 1

        status[
            "providers"
        ][provider.name] = {
            "healthy": healthy,
            "total": total,
        }

    return status


# ============================================================
# PERSISTENCE
# ============================================================

def _persist_all():

    try:

        metrics.persist()
        health_engine.persist()
        timeout_manager.persist()

    except Exception as exc:

        log_event(
            "WARN",
            "persist_all_failed",
            error=str(exc),
        )


def _persistence_loop():

    while True:

        time.sleep(
            CONFIG.persist_every_seconds
        )

        _persist_all()


threading.Thread(
    target=_persistence_loop,
    daemon=True,
).start()

atexit.register(
    _persist_all
)


# ============================================================
# FASTAPI
# ============================================================

from fastapi import (
    FastAPI,
    HTTPException,
    Request,
    Depends,
)

from fastapi.responses import (
    JSONResponse,
)

from fastapi.exceptions import (
    RequestValidationError,
)

from fastapi.middleware.cors import (
    CORSMiddleware,
)

from pydantic import (
    BaseModel,
    Field,
    field_validator,
)


app = FastAPI(
    title="LLM Gateway",
    version="4.0",
    description=(
        "LLM Gateway com "
        "failover, circuit breaker, "
        "cache e controle de TPM."
    ),
    docs_url="/docs",
    redoc_url=None,
)


if CONFIG.cors_origins:

    origins = (
        ["*"]
        if CONFIG.cors_origins.strip()
        == "*"
        else [
            origin.strip()
            for origin
            in CONFIG.cors_origins.split(",")
        ]
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# ============================================================
# OPENAI ERROR FORMAT
# ============================================================

def build_openai_error(
    message,
    error_type="invalid_request_error",
    code=None,
):
    return {
        "error": {
            "message": message,
            "type": error_type,
            "code": code,
        }
    }


# ============================================================
# AUTH
# ============================================================

def require_api_key(
    request: Request,
):

    if not CONFIG.require_auth:
        return

    authorization = request.headers.get(
        "authorization",
        "",
    )

    token = ""

    if authorization.startswith(
        "Bearer "
    ):
        token = authorization[
            len("Bearer "):
        ]

    if (
        not CONFIG.api_key
        or token != CONFIG.api_key
    ):
        raise HTTPException(
            status_code=401,
            detail="unauthorized",
        )


# ============================================================
# MODELS
# ============================================================

class ChatMessage(
    BaseModel
):
    role: str
    content: str

    @field_validator("role")
    @classmethod
    def validate_role(cls, value):

        if value not in (
            "system",
            "user",
            "assistant",
        ):
            return "user"

        return value


class ChatRequest(
    BaseModel
):
    messages: List[
        ChatMessage
    ]

    priority: int = Field(
        default=5,
        ge=1,
        le=10,
    )

    temperature: float = 0.7

    max_tokens: Optional[
        int
    ] = None

    stream: bool = False

    @field_validator("messages")
    @classmethod
    def validate_messages(
        cls,
        value,
    ):

        if not value:
            raise ValueError(
                "messages não pode ser vazio"
            )

        return value

    @field_validator(
        "temperature",
        mode="after",
    )
    @classmethod
    def clamp_temperature(
        cls,
        value,
    ):

        if value is None:
            return 0.7

        return max(
            0.0,
            min(
                float(value),
                2.0,
            ),
        )

    @field_validator(
        "max_tokens",
        mode="after",
    )
    @classmethod
    def clamp_max_tokens(
        cls,
        value,
    ):

        if (
            value is None
            or value <= 0
        ):
            return None

        return min(
            int(value),
            CONFIG.max_tokens_hard_cap,
        )


def _messages_to_dicts(
    messages,
):
    return [
        message.model_dump()
        for message in messages
    ]


# ============================================================
# ENDPOINT /chat
# ============================================================

@app.post(
    "/chat",
    dependencies=[
        Depends(require_api_key)
    ],
)
def chat(
    req: ChatRequest,
):

    try:

        messages = (
            _messages_to_dicts(
                req.messages
            )
        )

        future = submit_task(
            messages,
            priority=req.priority,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
        )

        result = future.result(
            timeout=(
                CONFIG.timeout
                * CONFIG.max_attempts
                + 30
            )
        )

        return {
            "response": result
        }

    except NoProvidersAvailableError as exc:

        raise HTTPException(
            status_code=503,
            detail=str(exc),
        )

    except Exception as exc:

        raise HTTPException(
            status_code=502,
            detail=str(exc),
        )


# ============================================================
# OPENAI COMPAT
# ============================================================

@app.post(
    "/v1/chat/completions",
    dependencies=[
        Depends(require_api_key)
    ],
)
def openai_chat_completions(
    req: ChatRequest,
):

    request_id = new_request_id()

    try:

        messages = (
            _messages_to_dicts(
                req.messages
            )
        )

        result_text = execute_protected(
            messages,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
        )

    except NoProvidersAvailableError as exc:

        raise HTTPException(
            status_code=503,
            detail=str(exc),
        )

    except Exception as exc:

        raise HTTPException(
            status_code=502,
            detail=str(exc),
        )

    completion_tokens = max(
        1,
        len(result_text.split()),
    )

    return {
        "id": (
            f"chatcmpl-{request_id}"
        ),
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "gateway",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": result_text,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": completion_tokens,
            "total_tokens": completion_tokens,
        },
    }


# ============================================================
# MODELS
# ============================================================

_MODEL_INFO = {
    "id": "gateway",
    "object": "model",
    "owned_by": "local",
    "created": int(time.time()),
}


@app.get("/v1/models")
def list_models():
    return {
        "object": "list",
        "data": [_MODEL_INFO],
    }


# ============================================================
# HEALTH
# ============================================================

@app.get("/health")
def health_endpoint():
    return health_status()


# ============================================================
# STATS
# ============================================================

@app.get("/stats")
def stats_endpoint():

    return {
        "metrics": metrics.snapshot(),
        "timeouts": timeout_manager.snapshot(),
        "queue_size": task_queue.qsize(),
        "cache_size": len(
            CACHE.store
        ),
        "redis_enabled": REDIS_ENABLED,
        "config": {
            "max_tokens_hard_cap": (
                CONFIG.max_tokens_hard_cap
            ),
            "groq_tpm_budget": (
                CONFIG.groq_tpm_budget
            ),
            "groq_tpm_safety_margin": (
                CONFIG.groq_tpm_safety_margin
            ),
            "require_auth": (
                CONFIG.require_auth
            ),
            "timeout": CONFIG.timeout,
            "max_attempts": (
                CONFIG.max_attempts
            ),
        },
    }


# ============================================================
# ROOT
# ============================================================

@app.get("/")
def root():

    return {
        "service": "llm-gateway",
        "status": "ok",
        "version": "4.0",
    }


# ============================================================
# VALIDATION ERROR HANDLER
# ============================================================

@app.exception_handler(
    RequestValidationError
)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):

    log_event(
        "WARN",
        "validation_error",
        path=str(
            request.url.path
        ),
        errors=str(
            exc.errors()
        ),
    )

    return JSONResponse(
        status_code=400,
        content=build_openai_error(
            (
                "Requisição inválida: "
                f"{exc.errors()}"
            ),
            code="validation_error",
        ),
    )


# ============================================================
# GENERIC ERROR HANDLER
# ============================================================

@app.exception_handler(
    Exception
)
async def generic_exception_handler(
    request: Request,
    exc: Exception,
):

    log_event(
        "ERROR",
        "unhandled_error",
        path=str(
            request.url.path
        ),
        error=str(exc),
    )

    return JSONResponse(
        status_code=500,
        content=build_openai_error(
            "internal_error",
            error_type="server_error",
            code="internal_error",
        ),
    )


# ============================================================
# STARTUP
# ============================================================

@app.on_event("startup")
async def on_startup():

    log_event(
        "INFO",
        "gateway_startup",
        total_keys=_total_keys,
        max_tokens_hard_cap=(
            CONFIG.max_tokens_hard_cap
        ),
        groq_tpm_budget=(
            CONFIG.groq_tpm_budget
        ),
        require_auth=(
            CONFIG.require_auth
        ),
        redis_enabled=REDIS_ENABLED,
    )


# ============================================================
# SHUTDOWN
# ============================================================

@app.on_event("shutdown")
async def on_shutdown():

    _persist_all()

    log_event(
        "INFO",
        "gateway_shutdown",
    )


# ============================================================
# DIRECT EXECUTION
# ============================================================

if __name__ == "__main__":

    import uvicorn

    host = os.getenv(
        "GATEWAY_HOST",
        "127.0.0.1",
    )

    port = int(
        os.getenv(
            "GATEWAY_PORT",
            "8000",
        )
    )

    uvicorn.run(
        app,
        host=host,
        port=port,
    )
