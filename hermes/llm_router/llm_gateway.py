import os
import time
import json
import uuid
import random
import hashlib
import logging
import threading
import itertools
import atexit
import queue
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, Future

import requests
from dotenv import load_dotenv

load_dotenv()


# ============================================================
# LOGGER
# ============================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gateway")


def log_event(level: str, message: str, **kwargs):
    payload = {
        "time": time.time(),
        "level": level,
        "msg": message,
        **kwargs,
    }

    print(
        json.dumps(
            payload,
            ensure_ascii=False,
        ),
        flush=True,
    )


def new_request_id() -> str:
    return str(uuid.uuid4())


# ============================================================
# CONFIG
# ============================================================

@dataclass
class GatewayConfig:
    timeout: int = int(
        os.getenv("GATEWAY_TIMEOUT", "60")
    )

    max_attempts: int = int(
        os.getenv("GATEWAY_MAX_ATTEMPTS", "20")
    )

    cache_enabled: bool = (
        os.getenv(
            "GATEWAY_CACHE_ENABLED",
            "true",
        ).lower()
        == "true"
    )

    cache_ttl: int = int(
        os.getenv(
            "GATEWAY_CACHE_TTL",
            "600",
        )
    )

    failure_threshold: int = int(
        os.getenv(
            "GATEWAY_FAILURE_THRESHOLD",
            "3",
        )
    )

    cooldown_seconds: int = int(
        os.getenv(
            "GATEWAY_COOLDOWN_SECONDS",
            "60",
        )
    )

    model_not_found_cooldown: int = int(
        os.getenv(
            "GATEWAY_MODEL_NOT_FOUND_COOLDOWN",
            "3600",
        )
    )

    max_retry_delay: float = float(
        os.getenv(
            "GATEWAY_MAX_RETRY_DELAY",
            "15",
        )
    )

    state_dir: str = os.getenv(
        "GATEWAY_STATE_DIR",
        "./.gateway_state",
    )

    persist_every_seconds: int = int(
        os.getenv(
            "GATEWAY_PERSIST_EVERY",
            "20",
        )
    )

    max_tracked_entries: int = int(
        os.getenv(
            "GATEWAY_MAX_TRACKED_ENTRIES",
            "500",
        )
    )

    max_tokens_hard_cap: int = int(
        os.getenv(
            "GATEWAY_MAX_TOKENS_CAP",
            "4096",
        )
    )

    groq_tpm_budget: int = int(
        os.getenv(
            "GROQ_TPM_BUDGET",
            "7500",
        )
    )

    groq_tpm_safety_margin: int = int(
        os.getenv(
            "GROQ_TPM_SAFETY_MARGIN",
            "500",
        )
    )

    require_auth: bool = (
        os.getenv(
            "GATEWAY_REQUIRE_AUTH",
            "false",
        ).lower()
        == "true"
    )

    api_key: str = os.getenv(
        "GATEWAY_API_KEY",
        "",
    )

    cors_origins: str = os.getenv(
        "GATEWAY_CORS_ORIGINS",
        "",
    )

    dynamic_models: bool = (
        os.getenv(
            "GATEWAY_DYNAMIC_MODELS",
            "true",
        ).lower()
        == "true"
    )

    model_refresh_seconds: int = int(
        os.getenv(
            "GATEWAY_MODEL_REFRESH_SECONDS",
            "900",
        )
    )


CONFIG = GatewayConfig()

os.makedirs(
    CONFIG.state_dir,
    exist_ok=True,
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
    metadata: Dict[str, Any] = field(
        default_factory=dict
    )

    def latency(self) -> float:
        return time.time() - self.start_time


# ============================================================
# STATIC MODEL POOLS
# ============================================================

GROQ_MODELS = [
    "openai/gpt-oss-120b",
    "qwen/qwen3.6-27b",
    "qwen/qwen3-32b",
    "qwen-qwq-32b",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "groq/compound",
    "groq/compound-mini",
    "openai/gpt-oss-20b",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
]


GEMINI_MODELS = [
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-3-pro-preview",
    "gemini-3.1-pro-preview",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
]


OPENROUTER_FALLBACK_MODELS = [
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    "z-ai/glm-5.2:free",
    "nvidia/nemotron-3.5-lightning:free",
    "liquid/lfm-2.5-2.6b:free",
    "poolside/laguna-s-2.1:free",
    "poolside/laguna-xs-2.1:free",
    "thinkingmachines/inkling:free",
    "thinkingmachines/inkling-small:free",
    "cohere/north-mini-code:free",
    "dots-studio/dots-3-note-preview:free",
]


# ============================================================
# PROVIDERS
# ============================================================

@dataclass
class ProviderConfig:
    name: str
    priority: int
    type: str
    url: str
    keys: List[Optional[str]]
    models: List[str]
    configured_models: List[str]


PROVIDERS: Dict[str, ProviderConfig] = {
    "groq": ProviderConfig(
        name="groq",
        priority=1,
        type="openai",
        url=(
            "https://api.groq.com/"
            "openai/v1/chat/completions"
        ),
        keys=[
            os.getenv("GROQ_KEY_1"),
            os.getenv("GROQ_KEY_2"),
            os.getenv("GROQ_KEY_3"),
        ],
        models=list(GROQ_MODELS),
        configured_models=list(GROQ_MODELS),
    ),

    "gemini": ProviderConfig(
        name="gemini",
        priority=2,
        type="gemini",
        url=(
            "https://generativelanguage."
            "googleapis.com/v1beta/models"
        ),
        keys=[
            os.getenv("GEMINI_KEY_1"),
            os.getenv("GEMINI_KEY_2"),
        ],
        models=list(GEMINI_MODELS),
        configured_models=list(GEMINI_MODELS),
    ),

    "openrouter": ProviderConfig(
        name="openrouter",
        priority=3,
        type="openai",
        url=(
            "https://openrouter.ai/"
            "api/v1/chat/completions"
        ),
        keys=[
            os.getenv("OPENROUTER_KEY_1"),
            os.getenv("OPENROUTER_KEY_2"),
            os.getenv("OPENROUTER_KEY_3"),
        ],
        models=list(
            OPENROUTER_FALLBACK_MODELS
        ),
        configured_models=list(
            OPENROUTER_FALLBACK_MODELS
        ),
    ),
}


TOTAL_KEYS = sum(
    1
    for provider in PROVIDERS.values()
    for key in provider.keys
    if key
)


if TOTAL_KEYS:
    log_event(
        "INFO",
        "providers_loaded",
        total_keys=TOTAL_KEYS,
    )
else:
    log_event(
        "WARN",
        "no_provider_keys_configured",
        total_keys=0,
    )


# ============================================================
# PERSISTENT JSON
# ============================================================

class PersistentJSON:
    def __init__(self, path: str):
        self.path = path
        self.lock = threading.Lock()

    def load(self, default):
        try:
            with open(
                self.path,
                "r",
                encoding="utf-8",
            ) as file:
                return json.load(file)
        except Exception:
            return default

    def save(self, data):
        temporary = (
            self.path + ".tmp"
        )

        try:
            with self.lock:
                with open(
                    temporary,
                    "w",
                    encoding="utf-8",
                ) as file:
                    json.dump(
                        data,
                        file,
                        ensure_ascii=False,
                    )

                os.replace(
                    temporary,
                    self.path,
                )

        except Exception as exc:
            log_event(
                "WARN",
                "persist_failed",
                path=self.path,
                error=str(exc),
            )


METRICS_STORE = PersistentJSON(
    os.path.join(
        CONFIG.state_dir,
        "metrics.json",
    )
)

HEALTH_STORE = PersistentJSON(
    os.path.join(
        CONFIG.state_dir,
        "health.json",
    )
)

TIMEOUTS_STORE = PersistentJSON(
    os.path.join(
        CONFIG.state_dir,
        "timeouts.json",
    )
)


# ============================================================
# CACHE
# ============================================================

class SmartCache:
    def __init__(self):
        self.store = {}
        self.lock = threading.Lock()

    def make_key(
        self,
        model,
        messages,
        extra=None,
    ):
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

            if item is None:
                return None

            if (
                time.time()
                - item["time"]
                > CONFIG.cache_ttl
            ):
                self.store.pop(
                    key,
                    None,
                )

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
# REDIS
# ============================================================

REDIS_ENABLED = False
redis_client = None


try:
    import redis

    redis_client = redis.Redis(
        host=os.getenv(
            "REDIS_HOST",
            "127.0.0.1",
        ),
        port=int(
            os.getenv(
                "REDIS_PORT",
                "6379",
            )
        ),
        db=int(
            os.getenv(
                "REDIS_DB",
                "0",
            )
        ),
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
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
        and redis_client is not None
    ):
        try:
            value = redis_client.get(
                key
            )

            if value is not None:
                return value

        except Exception as exc:
            log_event(
                "WARN",
                "redis_get_failed",
                error=str(exc),
            )

    return CACHE.get(key)


def cache_set(key, value):
    CACHE.set(
        key,
        value,
    )

    if (
        REDIS_ENABLED
        and redis_client is not None
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


# ============================================================
# METRICS
# ============================================================

class Metrics:
    def __init__(self):
        raw = METRICS_STORE.load({})

        self.data = defaultdict(
            lambda: {
                "success": 1,
                "fail": 1,
                "latency": 1.0,
            }
        )

        for key, value in raw.items():
            provider, separator, model = (
                key.partition("::")
            )

            if separator:
                self.data[
                    (
                        provider,
                        model,
                    )
                ] = value

    def update(
        self,
        provider,
        model,
        success,
        latency,
    ):
        item = self.data[
            (
                provider,
                model,
            )
        ]

        if success:
            item["success"] += 1
        else:
            item["fail"] += 1

        if latency > 0:
            item["latency"] = (
                item["latency"]
                + latency
            ) / 2.0

        self.prune()

    def score(
        self,
        provider,
        model,
    ):
        item = self.data[
            (
                provider,
                model,
            )
        ]

        total = max(
            1,
            item["success"]
            + item["fail"],
        )

        success_rate = (
            item["success"]
            / total
        )

        latency = max(
            item["latency"],
            0.1,
        )

        return (
            success_rate * 10.0
        ) / latency

    def prune(self):
        if (
            len(self.data)
            <= CONFIG.max_tracked_entries
        ):
            return

        worst = sorted(
            self.data.items(),
            key=lambda item: (
                item[1]["success"],
                -item[1]["fail"],
            ),
        )[:50]

        for key, _ in worst:
            self.data.pop(
                key,
                None,
            )

    def snapshot(self):
        return {
            f"{provider}:{model}": value
            for (
                provider,
                model,
            ), value in self.data.items()
        }

    def persist(self):
        METRICS_STORE.save(
            {
                f"{provider}::{model}": value
                for (
                    provider,
                    model,
                ), value in self.data.items()
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
    last_failure: float = 0.0
    cooldown_until: float = 0.0
    state: str = CircuitState.CLOSED
    success_streak: int = 0

    model_errors: int = 0
    rate_limits: int = 0
    payload_errors: int = 0
    empty_responses: int = 0
    timeouts: int = 0


class HealthEngine:
    def __init__(self):
        self.states = {}
        self.lock = threading.Lock()

        raw = HEALTH_STORE.load({})

        for key, value in raw.items():
            try:
                self.states[key] = (
                    HealthState(**value)
                )
            except Exception:
                self.states[key] = (
                    HealthState()
                )

    def key(
        self,
        provider,
        api_key,
        model,
    ):
        masked = (
            api_key or ""
        )[:6]

        return (
            f"{provider}:"
            f"{masked}:"
            f"{model}"
        )

    def get_state(self, key):
        if key not in self.states:
            self.states[key] = (
                HealthState()
            )

        return self.states[key]

    def is_available(
        self,
        provider,
        api_key,
        model,
    ):
        state_key = self.key(
            provider,
            api_key,
            model,
        )

        with self.lock:
            state = self.get_state(
                state_key
            )

            if (
                state.state
                == CircuitState.OPEN
            ):
                if (
                    time.time()
                    >= state.cooldown_until
                ):
                    state.state = (
                        CircuitState.HALF_OPEN
                    )

                    return True

                return False

            return True

    def on_success(
        self,
        provider,
        api_key,
        model,
    ):
        state_key = self.key(
            provider,
            api_key,
            model,
        )

        with self.lock:
            state = self.get_state(
                state_key
            )

            state.success_streak += 1
            state.failures = 0
            state.rate_limits = 0
            state.payload_errors = 0
            state.empty_responses = 0
            state.timeouts = 0

            if (
                state.state
                == CircuitState.HALF_OPEN
                and state.success_streak >= 2
            ):
                state.state = (
                    CircuitState.CLOSED
                )

    def on_failure(
        self,
        provider,
        api_key,
        model,
        kind,
    ):
        state_key = self.key(
            provider,
            api_key,
            model,
        )

        with self.lock:
            state = self.get_state(
                state_key
            )

            state.failures += 1
            state.last_failure = time.time()
            state.success_streak = 0

            if kind == "model_not_found":
                state.model_errors += 1

                state.state = (
                    CircuitState.OPEN
                )

                state.cooldown_until = (
                    time.time()
                    + CONFIG.model_not_found_cooldown
                )

                return

            if kind == "rate_limit":
                state.rate_limits += 1

                penalty = max(
                    CONFIG.cooldown_seconds
                    * 2,
                    90,
                )

            elif kind == "payload":
                state.payload_errors += 1
                penalty = 120

            elif kind == "timeout":
                state.timeouts += 1
                penalty = min(
                    180,
                    CONFIG.cooldown_seconds
                    * max(
                        1,
                        state.failures,
                    ),
                )

            elif kind == "empty_response":
                state.empty_responses += 1

                penalty = min(
                    180,
                    CONFIG.cooldown_seconds
                    * max(
                        1,
                        state.failures,
                    ),
                )

            else:
                penalty = min(
                    300,
                    CONFIG.cooldown_seconds
                    * max(
                        1,
                        state.failures,
                    ),
                )

            penalty += random.uniform(
                0,
                penalty * 0.15,
            )

            state.cooldown_until = (
                time.time()
                + penalty
            )

            if (
                state.failures
                >= CONFIG.failure_threshold
            ):
                state.state = (
                    CircuitState.OPEN
                )

    def health_score(
        self,
        provider,
        api_key,
        model,
    ):
        state_key = self.key(
            provider,
            api_key,
            model,
        )

        state = self.get_state(
            state_key
        )

        if (
            state.state
            == CircuitState.OPEN
        ):
            return 0.0

        penalty = (
            1
            + state.failures
            + state.rate_limits * 2
            + state.payload_errors
            + state.empty_responses
            + state.timeouts
        )

        bonus = (
            1
            + state.success_streak
        )

        return bonus / penalty

    def persist(self):
        with self.lock:
            HEALTH_STORE.save(
                {
                    key: vars(value)
                    for (
                        key,
                        value,
                    ) in self.states.items()
                }
            )


health_engine = HealthEngine()


# ============================================================
# KEY ROTATION
# ============================================================

class KeyManager:
    def __init__(self):
        self.usage = defaultdict(int)
        self.lock = threading.Lock()

    def valid_keys(
        self,
        provider,
        model,
    ):
        return [
            key
            for key in provider.keys
            if (
                key
                and health_engine.is_available(
                    provider.name,
                    key,
                    model,
                )
            )
        ]

    def best_key(
        self,
        provider,
        model,
    ):
        keys = self.valid_keys(
            provider,
            model,
        )

        if not keys:
            return None

        with self.lock:
            scored = [
                (
                    key,
                    health_engine.health_score(
                        provider.name,
                        key,
                        model,
                    )
                    - (
                        self.usage[
                            (
                                provider.name,
                                key,
                            )
                        ]
                        * 0.01
                    ),
                )
                for key in keys
            ]

        scored.sort(
            key=lambda item: -item[1]
        )

        return scored[0][0]

    def reserve(
        self,
        provider,
        key,
    ):
        with self.lock:
            self.usage[
                (
                    provider.name,
                    key,
                )
            ] += 1


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


class NoProvidersAvailableError(
    GatewayError
):
    pass


# ============================================================
# HTTP SESSION
# ============================================================

session = requests.Session()

session.headers.update(
    {
        "Content-Type": (
            "application/json"
        ),
        "User-Agent": (
            "automa-o-"
            "llm-gateway/8.0"
        ),
    }
)


# ============================================================
# TOKEN ESTIMATION
# ============================================================

def estimate_tokens(
    messages,
):
    text = "\n".join(
        str(
            message.get(
                "content",
                "",
            )
        )
        for message in messages
    )

    return max(
        1,
        (len(text) + 3) // 4,
    )


def calculate_output_budget(
    provider,
    messages,
    requested_max_tokens,
):
    requested = (
        CONFIG.max_tokens_hard_cap
        if requested_max_tokens is None
        else int(
            requested_max_tokens
        )
    )

    requested = max(
        1,
        min(
            requested,
            CONFIG.max_tokens_hard_cap,
        ),
    )

    if provider.name == "groq":
        estimated_input = (
            estimate_tokens(
                messages
            )
        )

        safe_budget = (
            CONFIG.groq_tpm_budget
            - CONFIG.groq_tpm_safety_margin
            - estimated_input
        )

        safe_budget = max(
            256,
            safe_budget,
        )

        requested = min(
            requested,
            safe_budget,
        )

    return max(
        1,
        requested,
    )


# ============================================================
# REQUEST PAYLOADS
# ============================================================

def build_openai_payload(
    model,
    messages,
    temperature,
    max_tokens,
):
    return {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }


def build_gemini_payload(
    messages,
    temperature,
    max_tokens,
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

        content = str(
            message.get(
                "content",
                "",
            )
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

    payload = {
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": (
                max_tokens
            ),
        },
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
# RESPONSE PARSING
# ============================================================

def safe_extract_text(data):
    try:
        value = (
            data["choices"][0]
            ["message"]
            ["content"]
        )

        if isinstance(
            value,
            str,
        ):
            return value

    except Exception:
        pass

    try:
        parts = (
            data["candidates"][0]
            ["content"]
            ["parts"]
        )

        result = []

        for part in parts:
            if isinstance(
                part,
                dict,
            ):
                text = part.get(
                    "text"
                )

                if isinstance(
                    text,
                    str,
                ):
                    result.append(
                        text
                    )

        if result:
            return "".join(
                result
            )

    except Exception:
        pass

    return ""


# ============================================================
# FAILURE CLASSIFICATION
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
# PROVIDER REQUEST
# ============================================================

def send_request(
    provider,
    model,
    key,
    payload,
    timeout,
):
    headers = {
        "Content-Type": (
            "application/json"
        )
    }

    if provider.type == "openai":
        headers["Authorization"] = (
            f"Bearer {key}"
        )

        if provider.name == "openrouter":
            headers[
                "HTTP-Referer"
            ] = os.getenv(
                "OPENROUTER_REFERER",
                "http://127.0.0.1",
            )

            headers["X-Title"] = (
                os.getenv(
                    "OPENROUTER_TITLE",
                    "Automa-O LLM Gateway",
                )
            )

        url = provider.url

    else:
        url = (
            f"{provider.url}/"
            f"{model}:generateContent"
        )

        headers = {
            "Content-Type": (
                "application/json"
            )
        }

    params = None

    if provider.type == "gemini":
        params = {
            "key": key
        }

    try:
        response = session.post(
            url,
            headers=headers,
            params=params,
            json=payload,
            timeout=timeout,
        )

    except requests.Timeout as exc:
        raise GatewayTimeoutError(
            str(exc)
        ) from exc

    except requests.RequestException as exc:
        raise ProviderError(
            str(exc)
        ) from exc

    body = response.text[:1000]

    if response.status_code == 429:
        raise RateLimitError(
            f"http_429: {body}"
        )

    if response.status_code == 413:
        raise PayloadTooLargeError(
            f"http_413: {body}"
        )

    if response.status_code == 404:
        raise ModelNotFoundError(
            f"http_404: {body}"
        )

    if response.status_code >= 500:
        raise ProviderError(
            f"http_{response.status_code}: "
            f"{body}"
        )

    if response.status_code >= 400:
        raise ProviderError(
            f"http_{response.status_code}: "
            f"{body}"
        )

    try:
        data = response.json()

    except ValueError as exc:
        raise ProviderError(
            f"invalid_json_response: {exc}"
        ) from exc

    text = safe_extract_text(data)

    if not text.strip():
        raise EmptyResponseError(
            "empty_response"
        )

    return text


# ============================================================
# DYNAMIC MODEL DISCOVERY
# ============================================================

model_refresh_lock = (
    threading.Lock()
)

last_model_refresh = 0.0


def discover_groq():
    provider = PROVIDERS["groq"]

    keys = [
        key
        for key in provider.keys
        if key
    ]

    if not keys:
        return list(
            GROQ_MODELS
        )

    try:
        response = requests.get(
            (
                "https://api.groq.com/"
                "openai/v1/models"
            ),
            headers={
                "Authorization": (
                    f"Bearer {keys[0]}"
                )
            },
            timeout=15,
        )

        response.raise_for_status()

        active = {
            str(
                item.get(
                    "id",
                    "",
                )
            )
            for item
            in response.json().get(
                "data",
                [],
            )
        }

        selected = [
            model
            for model in GROQ_MODELS
            if model in active
        ]

        if selected:
            return selected

        candidates = [
            model
            for model in active
            if any(
                term in model.lower()
                for term in (
                    "gpt-oss",
                    "qwen",
                    "compound",
                    "llama",
                    "reason",
                )
            )
        ]

        candidates.sort()

        return candidates[:20]

    except Exception as exc:
        log_event(
            "WARN",
            "groq_model_discovery_failed",
            error=str(exc),
        )

        return list(
            GROQ_MODELS
        )


def discover_gemini():
    provider = PROVIDERS["gemini"]

    keys = [
        key
        for key in provider.keys
        if key
    ]

    if not keys:
        return list(
            GEMINI_MODELS
        )

    try:
        response = requests.get(
            (
                "https://generativelanguage."
                "googleapis.com/v1beta/models"
            ),
            params={
                "key": keys[0]
            },
            timeout=15,
        )

        response.raise_for_status()

        active = set()

        for item in response.json().get(
            "models",
            [],
        ):
            name = str(
                item.get(
                    "name",
                    "",
                )
            )

            methods = item.get(
                "supportedGenerationMethods",
                [],
            )

            if (
                not name
                or (
                    "generateContent"
                    not in methods
                )
            ):
                continue

            active.add(
                name.split(
                    "/models/",
                    1,
                )[-1]
            )

        selected = [
            model
            for model in GEMINI_MODELS
            if model in active
        ]

        if selected:
            return selected

        candidates = [
            model
            for model in active
            if "gemini" in model.lower()
        ]

        candidates.sort()

        return candidates[:20]

    except Exception as exc:
        log_event(
            "WARN",
            "gemini_model_discovery_failed",
            error=str(exc),
        )

        return list(
            GEMINI_MODELS
        )


def discover_openrouter():
    provider = (
        PROVIDERS["openrouter"]
    )

    keys = [
        key
        for key in provider.keys
        if key
    ]

    if not keys:
        return list(
            OPENROUTER_FALLBACK_MODELS
        )

    try:
        response = requests.get(
            (
                "https://openrouter.ai/"
                "api/v1/models"
            ),
            headers={
                "Authorization": (
                    f"Bearer {keys[0]}"
                )
            },
            timeout=15,
        )

        response.raise_for_status()

        active = {
            str(
                item.get(
                    "id",
                    "",
                )
            )
            for item
            in response.json().get(
                "data",
                [],
            )
        }

        selected = [
            model
            for model
            in OPENROUTER_FALLBACK_MODELS
            if model in active
        ]

        if (
            "openrouter/free"
            in active
        ):
            selected.insert(
                0,
                "openrouter/free",
            )

        if selected:
            return selected

        candidates = [
            model
            for model in active
            if (
                ":free" in model
                and any(
                    term in model.lower()
                    for term in (
                        "qwen",
                        "nemotron",
                        "gemma",
                        "llama",
                        "glm",
                        "reason",
                        "thinking",
                        "code",
                        "hermes",
                        "liquid",
                    )
                )
            )
        ]

        candidates.sort()

        return candidates[:30]

    except Exception as exc:
        log_event(
            "WARN",
            "openrouter_model_discovery_failed",
            error=str(exc),
        )

        return list(
            OPENROUTER_FALLBACK_MODELS
        )


def refresh_models(
    force=False,
):
    global last_model_refresh

    if (
        not CONFIG.dynamic_models
        and not force
    ):
        return

    now = time.time()

    with model_refresh_lock:
        if (
            not force
            and (
                now
                - last_model_refresh
                < CONFIG.model_refresh_seconds
            )
        ):
            return

        groq_models = (
            discover_groq()
        )

        gemini_models = (
            discover_gemini()
        )

        openrouter_models = (
            discover_openrouter()
        )

        if groq_models:
            PROVIDERS[
                "groq"
            ].models = groq_models

        if gemini_models:
            PROVIDERS[
                "gemini"
            ].models = gemini_models

        if openrouter_models:
            PROVIDERS[
                "openrouter"
            ].models = (
                openrouter_models
            )

        last_model_refresh = now

        log_event(
            "INFO",
            "models_refreshed",
            groq_models=len(
                PROVIDERS[
                    "groq"
                ].models
            ),
            gemini_models=len(
                PROVIDERS[
                    "gemini"
                ].models
            ),
            openrouter_models=len(
                PROVIDERS[
                    "openrouter"
                ].models
            ),
        )


# ============================================================
# TIMEOUT MANAGER
# ============================================================

class TimeoutManager:
    def __init__(self):
        self.history = defaultdict(
            lambda: CONFIG.timeout
        )

        raw = TIMEOUTS_STORE.load(
            {}
        )

        for key, value in raw.items():
            provider, separator, model = (
                key.partition("::")
            )

            if separator:
                self.history[
                    (
                        provider,
                        model,
                    )
                ] = float(value)

    def get(
        self,
        provider,
        model,
    ):
        return min(
            120.0,
            max(
                5.0,
                self.history[
                    (
                        provider,
                        model,
                    )
                ],
            ),
        )

    def update(
        self,
        provider,
        model,
        latency,
        success,
    ):
        key = (
            provider,
            model,
        )

        current = self.history[key]

        if (
            success
            and latency > 0
        ):
            self.history[key] = (
                current
                + latency
            ) / 2.0

        else:
            self.history[key] = min(
                120.0,
                current * 1.5,
            )

    def snapshot(self):
        return {
            f"{provider}:{model}": value
            for (
                provider,
                model,
            ), value
            in self.history.items()
        }

    def persist(self):
        TIMEOUTS_STORE.save(
            {
                f"{provider}::{model}": value
                for (
                    provider,
                    model,
                ), value
                in self.history.items()
            }
        )


timeout_manager = (
    TimeoutManager()
)


# ============================================================
# MODEL RANKING
# ============================================================

def reasoning_bonus(
    provider,
    model,
):
    name = model.lower()

    bonus = 0.0

    reasoning_terms = (
        "reason",
        "thinking",
        "qwen",
        "nemotron",
        "gpt-oss",
        "glm",
        "hermes",
        "pro",
    )

    if any(
        term in name
        for term in reasoning_terms
    ):
        bonus += 1.5

    if (
        provider.name == "gemini"
        and "pro" in name
    ):
        bonus += 1.5

    if (
        provider.name == "groq"
        and (
            "gpt-oss-120b"
            in name
            or "qwen" in name
        )
    ):
        bonus += 1.0

    if (
        provider.name == "openrouter"
        and (
            "nemotron-3-ultra"
            in name
            or "nemotron-3-super"
            in name
        )
    ):
        bonus += 1.0

    return bonus


def rank_attempts():
    refresh_models()

    attempts = []

    for provider in (
        PROVIDERS.values()
    ):
        for model in provider.models:
            key = (
                key_manager.best_key(
                    provider,
                    model,
                )
            )

            if not key:
                continue

            score = (
                -provider.priority
                + metrics.score(
                    provider.name,
                    model,
                )
                + health_engine.health_score(
                    provider.name,
                    key,
                    model,
                )
                + reasoning_bonus(
                    provider,
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
# BACKOFF
# ============================================================

def compute_backoff(
    attempt,
):
    delay = min(
        CONFIG.max_retry_delay,
        0.5
        * (
            2 ** min(
                attempt,
                6,
            )
        ),
    )

    return delay + random.uniform(
        0,
        delay * 0.2,
    )


# ============================================================
# CORE EXECUTION
# ============================================================

def execute(
    messages: List[
        Dict[str, str]
    ],
    temperature: float = 0.7,
    max_tokens: Optional[int] = None,
):
    context = RequestContext(
        request_id=new_request_id(),
        start_time=time.time(),
    )

    if not messages:
        raise GatewayError(
            "messages_empty"
        )

    temperature = max(
        0.0,
        min(
            float(temperature),
            2.0,
        ),
    )

    if max_tokens is not None:
        max_tokens = max(
            1,
            min(
                int(max_tokens),
                CONFIG.max_tokens_hard_cap,
            ),
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
                request_id=(
                    context.request_id
                ),
            )

            return cached

    attempts = rank_attempts()

    if not attempts:
        raise NoProvidersAvailableError(
            "Nenhum provider disponível "
            "(sem chaves ou circuitos abertos)."
        )

    last_error = (
        "unknown_error"
    )

    attempted = set()

    for index, attempt in enumerate(
        attempts[
            :CONFIG.max_attempts
        ]
    ):
        provider = attempt[
            "provider"
        ]

        model = attempt[
            "model"
        ]

        key = attempt[
            "key"
        ]

        identity = (
            provider.name,
            model,
        )

        if identity in attempted:
            continue

        attempted.add(
            identity
        )

        context.provider = (
            provider.name
        )

        context.model = model
        context.attempt = index

        output_budget = (
            calculate_output_budget(
                provider,
                messages,
                max_tokens,
            )
        )

        timeout = (
            timeout_manager.get(
                provider.name,
                model,
            )
        )

        if (
            provider.type
            == "openai"
        ):
            payload = (
                build_openai_payload(
                    model,
                    messages,
                    temperature,
                    output_budget,
                )
            )

        else:
            payload = (
                build_gemini_payload(
                    messages,
                    temperature,
                    output_budget,
                )
            )

        log_event(
            "INFO",
            "attempt",
            request_id=(
                context.request_id
            ),
            provider=(
                provider.name
            ),
            model=model,
            attempt=index,
            estimated_input_tokens=(
                estimate_tokens(
                    messages
                )
            ),
            output_budget=(
                output_budget
            ),
        )

        start = time.time()

        try:
            key_manager.reserve(
                provider,
                key,
            )

            result = send_request(
                provider,
                model,
                key,
                payload,
                timeout,
            )

            latency = (
                time.time()
                - start
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
                request_id=(
                    context.request_id
                ),
                provider=(
                    provider.name
                ),
                model=model,
                latency=latency,
            )

            return result

        except Exception as exc:
            last_error = (
                str(exc)
                or exc.__class__.__name__
            )

            kind = (
                classify_failure(
                    exc
                )
            )

            metrics.update(
                provider.name,
                model,
                False,
                0,
            )

            health_engine.on_failure(
                provider.name,
                key,
                model,
                kind,
            )

            timeout_manager.update(
                provider.name,
                model,
                0,
                False,
            )

            log_event(
                "WARN",
                "failure",
                request_id=(
                    context.request_id
                ),
                provider=(
                    provider.name
                ),
                model=model,
                attempt=index,
                kind=kind,
                error=last_error,
            )

            if (
                kind
                == "model_not_found"
            ):
                refresh_models(
                    force=True
                )
                continue

            if kind in (
                "rate_limit",
                "payload",
            ):
                continue

            time.sleep(
                compute_backoff(
                    index
                )
            )

    raise GatewayError(
        "all_failed | "
        f"{last_error}"
    )


# ============================================================
# RATE LIMITER
# ============================================================

class RateLimiter:
    def __init__(
        self,
        rate_per_sec=10,
        capacity=20,
    ):
        self.rate = rate_per_sec
        self.capacity = capacity
        self.tokens = float(
            capacity
        )
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


rate_limiter = RateLimiter()


# ============================================================
# IN-FLIGHT COALESCING
# ============================================================

class InFlightRegistry:
    def __init__(self):
        self.events = {}
        self.lock = threading.Lock()

    def get(self, key):
        with self.lock:
            return self.events.get(
                key
            )

    def set(
        self,
        key,
        event,
    ):
        with self.lock:
            self.events[key] = event

    def delete(self, key):
        with self.lock:
            self.events.pop(
                key,
                None,
            )


inflight = (
    InFlightRegistry()
)


# ============================================================
# BACKPRESSURE
# ============================================================

class BackpressureController:
    def __init__(
        self,
        max_queue=100,
    ):
        self.queue_size = 0
        self.max_queue = (
            max_queue
        )
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


# ============================================================
# EXECUTION WRAPPERS
# ============================================================

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

    existing = (
        inflight.get(
            cache_key
        )
    )

    if existing:
        existing.wait()

        cached = cache_get(
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


executor = (
    ThreadPoolExecutor(
        max_workers=20
    )
)


def execute_async(
    messages,
    temperature=0.7,
    max_tokens=None,
):
    return executor.submit(
        execute_protected,
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
        for messages
        in batch_messages
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


def execute_stream(
    messages,
):
    result = (
        execute_protected(
            messages
        )
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
# PRIORITY QUEUE
# ============================================================

task_queue = (
    queue.PriorityQueue()
)

priority_counter = (
    itertools.count()
)


def submit_task(
    messages,
    priority=5,
    temperature=0.7,
    max_tokens=None,
):
    future: Future = (
        Future()
    )

    tie_breaker = next(
        priority_counter
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

        try:
            if not future.set_running_or_notify_cancel():
                continue

            future.set_result(
                execute_protected(
                    messages,
                    temperature,
                    max_tokens,
                )
            )

        except Exception as exc:
            future.set_exception(
                exc
            )

            log_event(
                "WARN",
                "worker_task_failed",
                error=str(exc),
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
    PLUGINS.append(
        func
    )

    return func


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
    result = {
        "status": "ok",
        "providers": {},
        "queue_size": (
            task_queue.qsize()
        ),
        "cache_size": len(
            CACHE.store
        ),
        "redis_enabled": (
            REDIS_ENABLED
        ),
    }

    for provider in (
        PROVIDERS.values()
    ):
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

        result[
            "providers"
        ][
            provider.name
        ] = {
            "healthy": healthy,
            "total": total,
            "models": len(
                provider.models
            ),
        }

    return result


# ============================================================
# PERSISTENCE LOOP
# ============================================================

def persist_all():
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


def persistence_loop():
    while True:
        time.sleep(
            CONFIG.persist_every_seconds
        )

        persist_all()


threading.Thread(
    target=persistence_loop,
    daemon=True,
).start()

atexit.register(
    persist_all
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
    version="8.0",
    description=(
        "Multi-provider LLM gateway "
        "with Redis, dynamic model "
        "discovery, health scoring, "
        "reasoning ranking and "
        "automatic failover."
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
            value.strip()
            for value
            in CONFIG.cors_origins.split(
                ","
            )
            if value.strip()
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
# AUTH
# ============================================================

def require_api_key(
    request: Request,
):
    if not CONFIG.require_auth:
        return

    authorization = (
        request.headers.get(
            "authorization",
            "",
        )
    )

    token = ""

    if authorization.startswith(
        "Bearer "
    ):
        token = authorization[
            7:
        ]

    if (
        not CONFIG.api_key
        or token
        != CONFIG.api_key
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

    @field_validator(
        "role"
    )
    @classmethod
    def validate_role(
        cls,
        value,
    ):
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

    @field_validator(
        "messages"
    )
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


def messages_to_dicts(
    messages,
):
    return [
        message.model_dump()
        for message in messages
    ]


# ============================================================
# ENDPOINTS
# ============================================================

@app.get("/")
def root():
    return {
        "service": "llm-gateway",
        "status": "ok",
        "version": "8.0",
    }


@app.get("/health")
def health_endpoint():
    return health_status()


@app.get(
    "/models/current"
)
def current_models():
    refresh_models()

    return {
        provider: config.models
        for provider, config
        in PROVIDERS.items()
    }


@app.get("/v1/models")
def list_models():
    return {
        "object": "list",
        "data": [
            {
                "id": "gateway",
                "object": "model",
                "owned_by": "local",
            }
        ],
    }


@app.get("/stats")
def stats_endpoint():
    return {
        "metrics": (
            metrics.snapshot()
        ),

        "timeouts": (
            timeout_manager.snapshot()
        ),

        "queue_size": (
            task_queue.qsize()
        ),

        "cache_size": len(
            CACHE.store
        ),

        "redis_enabled": (
            REDIS_ENABLED
        ),

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

            "timeout": (
                CONFIG.timeout
            ),

            "max_attempts": (
                CONFIG.max_attempts
            ),

            "dynamic_models": (
                CONFIG.dynamic_models
            ),

            "providers": {
                name: {
                    "priority": (
                        provider.priority
                    ),

                    "type": (
                        provider.type
                    ),

                    "models": (
                        provider.models
                    ),

                    "configured_models": (
                        provider.configured_models
                    ),

                    "keys": sum(
                        1
                        for key
                        in provider.keys
                        if key
                    ),
                }
                for (
                    name,
                    provider,
                )
                in PROVIDERS.items()
            },
        },
    }


@app.post(
    "/chat",
    dependencies=[
        Depends(
            require_api_key
        )
    ],
)
def chat(
    request: ChatRequest,
):
    try:
        messages = (
            messages_to_dicts(
                request.messages
            )
        )

        future = submit_task(
            messages,
            priority=(
                request.priority
            ),
            temperature=(
                request.temperature
            ),
            max_tokens=(
                request.max_tokens
            ),
        )

        result = future.result(
            timeout=(
                CONFIG.timeout
                * CONFIG.max_attempts
                + 60
            )
        )

        return {
            "response": result
        }

    except NoProvidersAvailableError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc


@app.post(
    "/v1/chat/completions",
    dependencies=[
        Depends(
            require_api_key
        )
    ],
)
def openai_chat_completions(
    request: ChatRequest,
):
    request_id = new_request_id()

    try:
        messages = (
            messages_to_dicts(
                request.messages
            )
        )

        result = execute_protected(
            messages,
            temperature=(
                request.temperature
            ),
            max_tokens=(
                request.max_tokens
            ),
        )

    except NoProvidersAvailableError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc

    completion_tokens = max(
        1,
        len(
            result.split()
        ),
    )

    return {
        "id": (
            f"chatcmpl-{request_id}"
        ),

        "object": (
            "chat.completion"
        ),

        "created": int(
            time.time()
        ),

        "model": "gateway",

        "choices": [
            {
                "index": 0,

                "message": {
                    "role": (
                        "assistant"
                    ),
                    "content": result,
                },

                "finish_reason": (
                    "stop"
                ),
            }
        ],

        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": (
                completion_tokens
            ),
            "total_tokens": (
                completion_tokens
            ),
        },
    }


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.exception_handler(
    RequestValidationError
)
async def validation_handler(
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
        content={
            "error": {
                "message": (
                    "Requisição inválida"
                ),
                "type": (
                    "invalid_request_error"
                ),
                "code": (
                    "validation_error"
                ),
                "details": (
                    exc.errors()
                ),
            }
        },
    )


@app.exception_handler(
    Exception
)
async def generic_handler(
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
        content={
            "error": {
                "message": (
                    "internal_error"
                ),
                "type": (
                    "server_error"
                ),
                "code": (
                    "internal_error"
                ),
            }
        },
    )


# ============================================================
# STARTUP / SHUTDOWN
# ============================================================

@app.on_event(
    "startup"
)
async def startup():
    refresh_models(
        force=True
    )

    log_event(
        "INFO",
        "gateway_startup",
        version="8.0",
        total_keys=(
            TOTAL_KEYS
        ),
        redis_enabled=(
            REDIS_ENABLED
        ),
        max_tokens_hard_cap=(
            CONFIG.max_tokens_hard_cap
        ),
        groq_tpm_budget=(
            CONFIG.groq_tpm_budget
        ),
        groq_tpm_safety_margin=(
            CONFIG.groq_tpm_safety_margin
        ),
        providers={
            name: {
                "models": len(
                    provider.models
                ),
                "keys": sum(
                    1
                    for key
                    in provider.keys
                    if key
                ),
            }
            for (
                name,
                provider,
            )
            in PROVIDERS.items()
        },
    )


@app.on_event(
    "shutdown"
)
async def shutdown():
    persist_all()

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
