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
from dataclasses import dataclass
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


def log_event(level, message, **kwargs):
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
        )
    )


def new_request_id():
    return str(uuid.uuid4())


# ============================================================
# CONFIGURATION
# ============================================================

@dataclass
class GatewayConfig:

    timeout: int = int(
        os.getenv(
            "GATEWAY_TIMEOUT",
            "60",
        )
    )

    max_attempts: int = int(
        os.getenv(
            "GATEWAY_MAX_ATTEMPTS",
            "15",
        )
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

    max_retry_delay: int = int(
        os.getenv(
            "GATEWAY_MAX_RETRY_DELAY",
            "20",
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

    # --------------------------------------------------------
    # TOKEN LIMIT
    # --------------------------------------------------------

    max_tokens_hard_cap: int = int(
        os.getenv(
            "GATEWAY_MAX_TOKENS_CAP",
            "4096",
        )
    )

    # --------------------------------------------------------
    # GROQ TPM
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # AUTH
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # CORS
    # --------------------------------------------------------

    cors_origins: str = os.getenv(
        "GATEWAY_CORS_ORIGINS",
        "",
    )

    # --------------------------------------------------------
    # DYNAMIC MODELS
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # OPENROUTER
    # --------------------------------------------------------

    openrouter_only_free: bool = (
        os.getenv(
            "OPENROUTER_ONLY_FREE",
            "true",
        ).lower()
        == "true"
    )

    openrouter_max_models: int = int(
        os.getenv(
            "OPENROUTER_MAX_MODELS",
            "20",
        )
    )

    # --------------------------------------------------------
    # GROQ
    # --------------------------------------------------------

    groq_max_models: int = int(
        os.getenv(
            "GROQ_MAX_MODELS",
            "15",
        )
    )

    # --------------------------------------------------------
    # GEMINI
    # --------------------------------------------------------

    gemini_max_models: int = int(
        os.getenv(
            "GEMINI_MAX_MODELS",
            "15",
        )
    )


CONFIG = GatewayConfig()

os.makedirs(
    CONFIG.state_dir,
    exist_ok=True,
)


# ============================================================
# PROVIDER CONFIG
# ============================================================

@dataclass
class ProviderConfig:

    name: str
    priority: int
    type: str
    url: str
    keys: List[str]
    models: List[str]


# ============================================================
# FALLBACK MODELS
# ============================================================
#
# São apenas fallback.
# O gateway tenta atualizar as listas pelas APIs oficiais.
# ============================================================


GROQ_FALLBACK_MODELS = [

    # Melhor raciocínio geral
    "openai/gpt-oss-120b",

    # Mais rápido
    "openai/gpt-oss-20b",

    # Reasoning
    "qwen/qwen3.6-27b",

    # Agentic
    "groq/compound",

    # Agentic mais leve
    "groq/compound-mini",

    # Segurança / reasoning
    "openai/gpt-oss-safeguard-20b",

    # Outro modelo atual que pode aparecer na conta
    "minimaxai/minimax-m2.7",
]


GEMINI_FALLBACK_MODELS = [

    # Raciocínio profundo
    "gemini-3.1-pro-preview",

    # Flash mais novo
    "gemini-3.7-flash",

    # Flash potente
    "gemini-3.6-flash",

    # Flash atual
    "gemini-3.5-flash",

    # Econômico
    "gemini-3.5-flash-lite",

    # Econômico
    "gemini-3.1-flash-lite",

    # Flash frontier
    "gemini-3-flash-preview",
]


OPENROUTER_FALLBACK_MODELS = [

    # Router oficial de modelos gratuitos.
    "openrouter/free",

    # Modelos que apareceram na verificação anterior.
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    "nvidia/nemotron-3.5-lightning:free",
    "liquid/lfm-2.5-2.6b:free",
]


# ============================================================
# PROVIDERS
# ============================================================

PROVIDERS: Dict[
    str,
    ProviderConfig,
] = {

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

        models=list(
            GROQ_FALLBACK_MODELS
        ),
    ),

    "gemini": ProviderConfig(

        name="gemini",

        priority=2,

        type="gemini",

        url=(
            "https://generativelanguage.googleapis.com/"
            "v1beta/models"
        ),

        keys=[
            os.getenv("GEMINI_KEY_1"),
            os.getenv("GEMINI_KEY_2"),
        ],

        models=list(
            GEMINI_FALLBACK_MODELS
        ),
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
        detail=(
            "Nenhuma API key "
            "foi encontrada."
        ),
    )

else:

    log_event(
        "INFO",
        "providers_loaded",
        total_keys=_total_keys,
    )


# ============================================================
# PERSISTENT JSON
# ============================================================

class PersistentJSON:

    def __init__(
        self,
        path: str,
    ):
        self.path = path
        self.lock = threading.Lock()

    def load(
        self,
        default,
    ):

        try:

            with open(
                self.path,
                "r",
                encoding="utf-8",
            ) as file:

                return json.load(file)

        except Exception:

            return default

    def save(
        self,
        data,
    ):

        tmp = (
            self.path
            + ".tmp"
        )

        try:

            with self.lock:

                with open(
                    tmp,
                    "w",
                    encoding="utf-8",
                ) as file:

                    json.dump(
                        data,
                        file,
                        ensure_ascii=False,
                    )

                os.replace(
                    tmp,
                    self.path,
                )

        except Exception as exc:

            log_event(
                "WARN",
                "persist_failed",
                path=self.path,
                error=str(exc),
            )


_metrics_store = PersistentJSON(
    os.path.join(
        CONFIG.state_dir,
        "metrics.json",
    )
)


_health_store = PersistentJSON(
    os.path.join(
        CONFIG.state_dir,
        "health.json",
    )
)


_timeouts_store = PersistentJSON(
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

        self.lock = (
            threading.Lock()
        )

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
            raw.encode(
                "utf-8"
            )
        ).hexdigest()

    def get(
        self,
        key,
    ):

        with self.lock:

            item = self.store.get(
                key
            )

            if not item:
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

    def set(
        self,
        key,
        value,
    ):

        with self.lock:

            self.store[
                key
            ] = {
                "value": value,
                "time": time.time(),
            }


CACHE = SmartCache()


# ============================================================
# METRICS
# ============================================================

class Metrics:

    def __init__(self):

        raw = (
            _metrics_store.load(
                {}
            )
        )

        self.data = defaultdict(
            lambda: {
                "success": 1,
                "fail": 1,
                "latency": 1.0,
            }
        )

        for key, value in raw.items():

            parts = key.split(
                "::",
                1,
            )

            if len(parts) == 2:

                self.data[
                    (
                        parts[0],
                        parts[1],
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
            ) / 2

        self._prune()

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
            success_rate
            * 10
        ) / latency

    def _prune(self):

        if (
            len(self.data)
            <= CONFIG.max_tracked_entries
        ):
            return

        worst = sorted(
            self.data.items(),
            key=lambda x: (
                x[1]["success"],
                -x[1]["fail"],
            ),
        )[:50]

        for key, _ in worst:

            self.data.pop(
                key,
                None,
            )

    def snapshot(self):

        return {
            f"{provider}:{model}":
            value
            for (
                provider,
                model,
            ), value
            in self.data.items()
        }

    def persist(self):

        _metrics_store.save(
            {
                f"{provider}::{model}":
                value
                for (
                    provider,
                    model,
                ), value
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

    state: str = (
        CircuitState.CLOSED
    )

    success_streak: int = 0

    model_errors: int = 0

    rate_limits: int = 0

    payload_errors: int = 0

    empty_responses: int = 0


class HealthEngine:

    def __init__(self):

        self.states = {}

        self.lock = (
            threading.Lock()
        )

        raw = (
            _health_store.load(
                {}
            )
        )

        for key, value in raw.items():

            try:

                self.states[
                    key
                ] = HealthState(
                    **value
                )

            except Exception:

                self.states[
                    key
                ] = HealthState()

    def _key(
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

    def _get(
        self,
        key,
    ):

        if key not in self.states:

            self.states[
                key
            ] = HealthState()

        return self.states[
            key
        ]

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

            state = self._get(
                key
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

    def on_failure(
        self,
        provider,
        api_key,
        model,
        error,
        kind,
    ):

        key = self._key(
            provider,
            api_key,
            model,
        )

        with self.lock:

            state = self._get(
                key
            )

            state.failures += 1

            state.last_failure = (
                time.time()
            )

            state.success_streak = 0

            # ------------------------------------------------
            # MODELO INEXISTENTE
            # ------------------------------------------------

            if (
                kind
                == "model_not_found"
            ):

                state.model_errors += 1

                state.cooldown_until = (
                    time.time()
                    + CONFIG.model_not_found_cooldown
                )

                state.state = (
                    CircuitState.OPEN
                )

                return

            # ------------------------------------------------
            # RATE LIMIT
            # ------------------------------------------------

            if (
                kind
                == "rate_limit"
            ):

                state.rate_limits += 1

                penalty = min(
                    300,
                    max(
                        CONFIG.cooldown_seconds
                        * 2,
                        90,
                    ),
                )

            # ------------------------------------------------
            # REQUEST TOO LARGE
            # ------------------------------------------------

            elif (
                kind
                == "payload"
            ):

                state.payload_errors += 1

                penalty = 180

            # ------------------------------------------------
            # EMPTY RESPONSE
            # ------------------------------------------------

            elif (
                kind
                == "empty_response"
            ):

                state.empty_responses += 1

                penalty = min(
                    180,
                    CONFIG.cooldown_seconds
                    * state.failures,
                )

            # ------------------------------------------------
            # GENERIC
            # ------------------------------------------------

            else:

                penalty = min(
                    300,
                    CONFIG.cooldown_seconds
                    * state.failures,
                )

            penalty += (
                random.uniform(
                    0,
                    penalty * 0.15,
                )
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

            state = self._get(
                key
            )

            state.success_streak += 1

            state.failures = 0

            state.rate_limits = 0

            state.payload_errors = 0

            state.empty_responses = 0

            if (
                state.state
                == CircuitState.HALF_OPEN
                and state.success_streak
                >= 2
            ):

                state.state = (
                    CircuitState.CLOSED
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

        state = self._get(
            key
        )

        if (
            state.state
            == CircuitState.OPEN
        ):

            return 0

        penalty = (
            1
            + state.failures
            + state.rate_limits * 2
            + state.payload_errors
            + state.empty_responses
        )

        bonus = (
            1
            + state.success_streak
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

        self.usage = (
            defaultdict(int)
        )

        self.lock = (
            threading.Lock()
        )

    def _valid_keys(
        self,
        provider,
        model,
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
        provider,
        model,
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
                    - self.usage[
                        (
                            provider.name,
                            key,
                        )
                    ] * 0.01
                )

                scored.append(
                    (
                        key,
                        score,
                    )
                )

        scored.sort(
            key=lambda x: -x[1]
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
                (
                    provider.name,
                    key,
                )
            ] += 1


key_manager = (
    KeyManager()
)


# ============================================================
# ERRORS
# ============================================================

class GatewayError(Exception):
    pass


class RateLimitError(
    GatewayError
):
    pass


class ModelNotFoundError(
    GatewayError
):
    pass


class PayloadTooLargeError(
    GatewayError
):
    pass


class ProviderError(
    GatewayError
):
    pass


class GatewayTimeoutError(
    GatewayError
):
    pass


class EmptyResponseError(
    GatewayError
):
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
        "Content-Type":
            "application/json",

        "User-Agent":
            "automa-o-llm-gateway/6.0",
    }
)


# ============================================================
# MODEL DISCOVERY
# ============================================================

_model_refresh_lock = (
    threading.Lock()
)

_model_refresh_time = 0.0


def _extract_ids(
    data,
):

    ids = []

    for item in data:

        model_id = str(
            item.get(
                "id",
                ""
            )
        ).strip()

        if model_id:
            ids.append(
                model_id
            )

    return ids


# ============================================================
# GROQ DISCOVERY
# ============================================================

def discover_groq_models():

    keys = [
        key
        for key in PROVIDERS[
            "groq"
        ].keys
        if key
    ]

    if not keys:

        return list(
            GROQ_FALLBACK_MODELS
        )

    try:

        response = requests.get(
            "https://api.groq.com/"
            "openai/v1/models",

            headers={
                "Authorization":
                    f"Bearer {keys[0]}"
            },

            timeout=15,
        )

        response.raise_for_status()

        ids = _extract_ids(
            response.json().get(
                "data",
                [],
            )
        )

        # ----------------------------------------------------
        # Só modelos de texto relevantes para o gateway.
        # ----------------------------------------------------

        excluded = (
            "whisper",
            "speech",
            "guard",
            "tts",
            "audio",
            "orpheus",
            "prompt-guard",
        )

        candidates = [
            model
            for model in ids
            if not any(
                token in model.lower()
                for token in excluded
            )
        ]

        # Priorização explícita.
        preferred = [
            model
            for model in candidates
            if any(
                token in model.lower()
                for token in [
                    "gpt-oss",
                    "qwen",
                    "compound",
                    "minimax",
                    "llama",
                ]
            )
        ]

        if not preferred:

            preferred = candidates

        result = []

        for model in preferred:

            if model not in result:

                result.append(
                    model
                )

            if len(result) >= (
                CONFIG.groq_max_models
            ):
                break

        if result:

            return result

    except Exception as exc:

        log_event(
            "WARN",
            "groq_model_discovery_failed",
            error=str(exc),
        )

    return list(
        GROQ_FALLBACK_MODELS
    )


# ============================================================
# GEMINI DISCOVERY
# ============================================================

def discover_gemini_models():

    keys = [
        key
        for key in PROVIDERS[
            "gemini"
        ].keys
        if key
    ]

    if not keys:

        return list(
            GEMINI_FALLBACK_MODELS
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

        data = response.json().get(
            "models",
            [],
        )

        candidates = []

        for model in data:

            name = str(
                model.get(
                    "name",
                    ""
                )
            )

            if not name:
                continue

            model_id = name.split(
                "/models/",
                1
            )[-1]

            methods = model.get(
                "supportedGenerationMethods",
                [],
            )

            if (
                "generateContent"
                not in methods
            ):
                continue

            low = model_id.lower()

            if not (
                "gemini"
                in low
            ):
                continue

            # Priorizamos os modelos Gemini
            # mais novos/relevantes.
            if any(
                token in low
                for token in [
                    "3.1-pro",
                    "3.7-flash",
                    "3.6-flash",
                    "3.5-flash",
                    "3.1-flash",
                    "3-flash",
                    "2.5",
                ]
            ):

                candidates.append(
                    model_id
                )

        result = []

        for model in candidates:

            if model not in result:

                result.append(
                    model
                )

            if len(result) >= (
                CONFIG.gemini_max_models
            ):
                break

        if result:

            return result

    except Exception as exc:

        log_event(
            "WARN",
            "gemini_model_discovery_failed",
            error=str(exc),
        )

    return list(
        GEMINI_FALLBACK_MODELS
    )


# ============================================================
# OPENROUTER DISCOVERY
# ============================================================

def discover_openrouter_models():

    keys = [
        key
        for key in PROVIDERS[
            "openrouter"
        ].keys
        if key
    ]

    if not keys:

        return list(
            OPENROUTER_FALLBACK_MODELS
        )

    try:

        response = requests.get(
            "https://openrouter.ai/"
            "api/v1/models",

            headers={
                "Authorization":
                    f"Bearer {keys[0]}"
            },

            timeout=15,
        )

        response.raise_for_status()

        data = response.json().get(
            "data",
            [],
        )

        candidates = []

        for item in data:

            model_id = str(
                item.get(
                    "id",
                    ""
                )
            ).strip()

            if not model_id:
                continue

            low = model_id.lower()

            # ------------------------------------------------
            # Só modelos gratuitos.
            # ------------------------------------------------

            if (
                CONFIG.openrouter_only_free
                and ":free"
                not in model_id
                and model_id
                != "openrouter/free"
            ):
                continue

            # ------------------------------------------------
            # Priorizamos modelos de reasoning.
            # ------------------------------------------------

            if any(
                token in low
                for token in [
                    "reason",
                    "thinking",
                    "qwen",
                    "nemotron",
                    "gemma",
                    "llama",
                    "hermes",
                    "glm",
                    "liquid",
                    "openrouter/free",
                ]
            ):

                candidates.append(
                    model_id
                )

        # --------------------------------------------
        # Primeiro o router gratuito oficial.
        # --------------------------------------------

        result = []

        if "openrouter/free" in candidates:

            result.append(
                "openrouter/free"
            )

        for model in candidates:

            if model in result:
                continue

            result.append(
                model
            )

            if len(result) >= (
                CONFIG.openrouter_max_models
            ):
                break

        if result:

            return result

    except Exception as exc:

        log_event(
            "WARN",
            "openrouter_model_discovery_failed",
            error=str(exc),
        )

    return list(
        OPENROUTER_FALLBACK_MODELS
    )


# ============================================================
# GLOBAL REFRESH
# ============================================================

def refresh_models(
    force=False,
):

    global _model_refresh_time

    if not CONFIG.dynamic_models:
        return

    now = time.time()

    with _model_refresh_lock:

        if (
            not force
            and (
                now
                - _model_refresh_time
                < CONFIG.model_refresh_seconds
            )
        ):
            return

        # --------------------------------------------
        # Groq
        # --------------------------------------------

        PROVIDERS[
            "groq"
        ].models = (
            discover_groq_models()
        )

        # --------------------------------------------
        # Gemini
        # --------------------------------------------

        PROVIDERS[
            "gemini"
        ].models = (
            discover_gemini_models()
        )

        # --------------------------------------------
        # OpenRouter
        # --------------------------------------------

        PROVIDERS[
            "openrouter"
        ].models = (
            discover_openrouter_models()
        )

        _model_refresh_time = now

        log_event(
            "INFO",
            "models_refreshed",

            groq_count=len(
                PROVIDERS[
                    "groq"
                ].models
            ),

            gemini_count=len(
                PROVIDERS[
                    "gemini"
                ].models
            ),

            openrouter_count=len(
                PROVIDERS[
                    "openrouter"
                ].models
            ),
        )


refresh_models(
    force=False
)


# ============================================================
# TIMEOUT MANAGER
# ============================================================

class TimeoutManager:

    def __init__(self):

        self.base = (
            CONFIG.timeout
        )

        raw = (
            _timeouts_store.load(
                {}
            )
        )

        self.history = (
            defaultdict(
                lambda:
                self.base
            )
        )

        for key, value in raw.items():

            parts = key.split(
                "::",
                1,
            )

            if len(parts) == 2:

                self.history[
                    (
                        parts[0],
                        parts[1],
                    )
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
                    (
                        provider,
                        model,
                    )
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

        key = (
            provider,
            model,
        )

        current = (
            self.history[
                key
            ]
        )

        if success:

            self.history[
                key
            ] = (
                current
                + latency
            ) / 2

        else:

            self.history[
                key
            ] = min(
                120,
                current * 1.5,
            )

    def snapshot(self):

        return {
            f"{provider}:{model}":
            value
            for (
                provider,
                model,
            ), value
            in self.history.items()
        }

    def persist(self):

        _timeouts_store.save(
            {
                f"{provider}::{model}":
                value

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
# TOKEN ESTIMATION
# ============================================================

def estimate_tokens(
    messages,
):

    text = ""

    for message in messages:

        content = message.get(
            "content",
            "",
        )

        text += str(
            content
        )

        text += "\n"

    return max(
        1,
        len(text) // 4,
    )


def calculate_output_budget(
    provider,
    model,
    messages,
    requested_max_tokens,
):

    if (
        requested_max_tokens
        is None
    ):

        requested = (
            CONFIG.max_tokens_hard_cap
        )

    else:

        requested = int(
            requested_max_tokens
        )

    requested = max(
        256,
        requested,
    )

    requested = min(
        requested,
        CONFIG.max_tokens_hard_cap,
    )

    estimated_input = (
        estimate_tokens(
            messages
        )
    )

    # Groq recebe limite adicional
    # para evitar 413/TPM.
    if (
        provider.name
        == "groq"
    ):

        usable = max(
            1024,
            CONFIG.groq_tpm_budget
            - CONFIG.groq_tpm_safety_margin,
        )

        requested = min(
            requested,
            max(
                256,
                usable
                - estimated_input,
            ),
        )

    return max(
        256,
        requested,
    )


# ============================================================
# PAYLOAD BUILDERS
# ============================================================

def safe_extract_text(
    data,
):

    # OpenAI-compatible
    try:

        value = (
            data[
                "choices"
            ][0][
                "message"
            ][
                "content"
            ]
        )

        if isinstance(
            value,
            str,
        ):

            return value

    except Exception:
        pass

    # Gemini
    try:

        value = (
            data[
                "candidates"
            ][0][
                "content"
            ][
                "parts"
            ][0][
                "text"
            ]
        )

        if isinstance(
            value,
            str,
        ):

            return value

    except Exception:
        pass

    return ""


def build_openai_payload(
    model,
    messages,
    temperature,
    max_tokens,
):

    payload = {
        "model":
            model,

        "messages":
            messages,

        "temperature":
            temperature,
    }

    if max_tokens is not None:

        payload[
            "max_tokens"
        ] = max_tokens

    return payload


def build_gemini_payload(
    model,
    messages,
    temperature,
    max_tokens,
):

    role_map = {
        "user":
            "user",

        "assistant":
            "model",

        "model":
            "model",
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

        if (
            role
            == "system"
        ):

            system_parts.append(
                content
            )

            continue

        contents.append(
            {
                "role":
                    role_map.get(
                        role,
                        "user",
                    ),

                "parts":
                    [
                        {
                            "text":
                                content
                        }
                    ],
            }
        )

    generation_config = {
        "temperature":
            temperature
    }

    if max_tokens is not None:

        generation_config[
            "maxOutputTokens"
        ] = max_tokens

    payload = {
        "contents":
            contents,

        "generationConfig":
            generation_config,
    }

    if system_parts:

        payload[
            "systemInstruction"
        ] = {
            "parts":
                [
                    {
                        "text":
                            "\n".join(
                                system_parts
                            )
                    }
                ]
        }

    return payload


# ============================================================
# HTTP REQUEST
# ============================================================

def send_request(
    provider,
    model,
    key,
    payload,
    timeout,
):

    headers = {
        "Content-Type":
            "application/json"
    }

    if (
        provider.type
        == "openai"
    ):

        headers[
            "Authorization"
        ] = f"Bearer {key}"

    url = provider.url

    if (
        provider.type
        == "gemini"
    ):

        url = (
            f"{provider.url}/"
            f"{model}:generateContent"
            f"?key={key}"
        )

    try:

        response = (
            session.post(
                url,
                headers=headers,
                json=payload,
                timeout=timeout,
            )
        )

    except requests.Timeout as exc:

        raise GatewayTimeoutError(
            str(exc)
        ) from exc

    except requests.RequestException as exc:

        raise ProviderError(
            str(exc)
        ) from exc

    status = response.status_code

    body = response.text[:600]

    if status == 429:

        retry_after = (
            response.headers.get(
                "retry-after",
                "",
            )
        )

        raise RateLimitError(
            (
                "http_429 "
                f"retry_after={retry_after} "
                f"{body}"
            )
        )

    if status == 413:

        raise PayloadTooLargeError(
            f"http_413: {body}"
        )

    if status == 404:

        raise ModelNotFoundError(
            f"http_404: {body}"
        )

    if status >= 500:

        raise ProviderError(
            f"http_{status}: {body}"
        )

    if status >= 400:

        raise ProviderError(
            f"http_{status}: {body}"
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

    if (
        not text
        or not text.strip()
    ):

        raise EmptyResponseError(
            "empty_response"
        )

    return text


# ============================================================
# FAILURE CLASSIFICATION
# ============================================================

def classify_failure(
    error,
):

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
# RANKING
# ============================================================

def rank_attempts():

    refresh_models()

    attempts = []

    # --------------------------------------------
    # Cada provider
    # --------------------------------------------

    for provider in PROVIDERS.values():

        for model in provider.models:

            key = (
                key_manager.peek_key(
                    provider,
                    model,
                )
            )

            if not key:
                continue

            score = (
                provider.priority
                * -1
            )

            score += (
                metrics.score(
                    provider.name,
                    model,
                )
            )

            score += (
                health_engine.health_score(
                    provider.name,
                    key,
                    model,
                )
            )

            # ----------------------------------------
            # Reforça modelos de reasoning.
            # ----------------------------------------

            low = model.lower()

            reasoning_bonus = 0

            if any(
                token in low
                for token in [
                    "gpt-oss",
                    "qwen",
                    "nemotron",
                    "gemma",
                    "reason",
                    "thinking",
                    "pro",
                ]
            ):

                reasoning_bonus = 1.5

            # Gemini Pro ganha pequena preferência
            # para tarefas complexas.

            if (
                provider.name
                == "gemini"
                and "pro"
                in low
            ):

                reasoning_bonus += 1.5

            score += reasoning_bonus

            attempts.append(
                {
                    "provider":
                        provider,

                    "model":
                        model,

                    "key":
                        key,

                    "score":
                        score,
                }
            )

    attempts.sort(
        key=lambda x:
        -x["score"]
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
            2
            ** min(
                attempt,
                6,
            )
        ),
    )

    jitter = (
        delay * 0.2
    )

    return (
        delay
        + random.uniform(
            -jitter,
            jitter,
        )
    )


# ============================================================
# EXECUTION
# ============================================================

def execute(
    messages,
    temperature=0.7,
    max_tokens=None,
):

    context = RequestContext(
        request_id=
            new_request_id(),

        start_time=
            time.time(),
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

    # --------------------------------------------------------
    # CACHE KEY
    # --------------------------------------------------------

    cache_key = (
        CACHE.make_key(
            "auto",
            messages,
            {
                "temperature":
                    temperature,

                "max_tokens":
                    max_tokens,
            },
        )
    )

    # --------------------------------------------------------
    # CACHE LOOKUP
    # --------------------------------------------------------

    if CONFIG.cache_enabled:

        cached = cache_get(
            cache_key
        )

        if cached is not None:

            log_event(
                "INFO",
                "cache_hit",
                request_id=
                    context.request_id,
            )

            return cached

    # --------------------------------------------------------
    # RANKING
    # --------------------------------------------------------

    attempts = (
        rank_attempts()
    )

    if not attempts:

        raise NoProvidersAvailableError(
            "Nenhum provider disponível."
        )

    last_error = None

    attempted_pairs = set()

    # --------------------------------------------------------
    # FAILOVER LOOP
    # --------------------------------------------------------

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

        pair = (
            provider.name,
            model,
        )

        if pair in attempted_pairs:
            continue

        attempted_pairs.add(
            pair
        )

        context.provider = (
            provider.name
        )

        context.model = (
            model
        )

        context.attempt = (
            index
        )

        output_budget = (
            calculate_output_budget(
                provider,
                model,
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

        try:

            # ------------------------------------------------
            # PAYLOAD
            # ------------------------------------------------

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

                request_id=
                    context.request_id,

                provider=
                    provider.name,

                model=
                    model,

                attempt=
                    index,

                estimated_input_tokens=
                    estimated_input,

                output_budget=
                    output_budget,
            )

            start = time.time()

            key_manager.reserve_key(
                provider,
                key,
            )

            # ------------------------------------------------
            # REQUEST
            # ------------------------------------------------

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

            # ------------------------------------------------
            # SUCCESS
            # ------------------------------------------------

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

            if (
                CONFIG.cache_enabled
            ):

                cache_set(
                    cache_key,
                    result,
                )

            log_event(
                "INFO",
                "success",

                request_id=
                    context.request_id,

                provider=
                    provider.name,

                model=
                    model,

                latency=
                    latency,
            )

            return result

        except Exception as exc:

            last_error = (
                str(exc)
                or
                exc.__class__.__name__
            )

            kind = (
                classify_failure(
                    exc
                )
            )

            log_event(
                "WARN",
                "failure",

                request_id=
                    context.request_id,

                provider=
                    provider.name,

                model=
                    model,

                kind=
                    kind,

                error=
                    last_error,
            )

            # ------------------------------------------------
            # HEALTH
            # ------------------------------------------------

            health_engine.on_failure(
                provider.name,
                key,
                model,
                last_error,
                kind,
            )

            # ------------------------------------------------
            # METRICS
            # ------------------------------------------------

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

            # ------------------------------------------------
            # 404
            # ------------------------------------------------
            #
            # Modelo morreu / slug mudou.
            #
            # Atualiza modelos imediatamente.
            # ------------------------------------------------

            if (
                kind
                == "model_not_found"
            ):

                refresh_models(
                    force=True
                )

                continue

            # ------------------------------------------------
            # 413
            # ------------------------------------------------

            if (
                kind
                == "payload"
            ):

                continue

            # ------------------------------------------------
            # 429
            # ------------------------------------------------

            if (
                kind
                == "rate_limit"
            ):

                continue

            # ------------------------------------------------
            # OUTROS ERROS
            # ------------------------------------------------

            time.sleep(
                max(
                    0,
                    compute_backoff(
                        index
                    ),
                )
            )

    raise GatewayError(
        "all_failed | "
        + (
            last_error
            or "unknown_error"
        )
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

        self.rate = (
            rate_per_sec
        )

        self.capacity = (
            capacity
        )

        self.tokens = (
            capacity
        )

        self.last = (
            time.time()
        )

        self.lock = (
            threading.Lock()
        )

    def acquire(self):

        with self.lock:

            now = time.time()

            delta = (
                now
                - self.last
            )

            self.tokens = min(
                self.capacity,

                self.tokens
                + (
                    delta
                    * self.rate
                ),
            )

            self.last = now

            if (
                self.tokens
                >= 1
            ):

                self.tokens -= 1

                return True

            return False


rate_limiter = (
    RateLimiter()
)


# ============================================================
# IN-FLIGHT COALESCING
# ============================================================

class InFlightRegistry:

    def __init__(self):

        self.events = {}

        self.lock = (
            threading.Lock()
        )

    def get(
        self,
        key,
    ):

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

            self.events[
                key
            ] = event

    def delete(
        self,
        key,
    ):

        with self.lock:

            self.events.pop(
                key,
                None,
            )


inflight = (
    InFlightRegistry()
)


executor = (
    ThreadPoolExecutor(
        max_workers=20
    )
)


def execute_safe(
    messages,
    temperature=0.7,
    max_tokens=None,
):

    cache_key = (
        CACHE.make_key(
            "auto",
            messages,
            {
                "temperature":
                    temperature,

                "max_tokens":
                    max_tokens,
            },
        )
    )

    existing = (
        inflight.get(
            cache_key
        )
    )

    if existing:

        logger.info(
            "[COALESCED REQUEST]"
        )

        existing.wait()

        cached = cache_get(
            cache_key
        )

        if cached is not None:

            return cached

    event = (
        threading.Event()
    )

    inflight.set(
        cache_key,
        event,
    )

    try:

        while not rate_limiter.acquire():

            time.sleep(
                0.05
            )

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

        self.lock = (
            threading.Lock()
        )

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
# REDIS
# ============================================================

REDIS_ENABLED = False

redis_client = None


try:

    import redis

    redis_client = (
        redis.Redis(

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

            db=0,

            decode_responses=True,

            socket_connect_timeout=1,

            socket_timeout=1,
        )
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


def cache_get(
    key,
):

    if (
        REDIS_ENABLED
        and redis_client
    ):

        try:

            value = (
                redis_client.get(
                    key
                )
            )

            if value is not None:

                return value

        except Exception as exc:

            log_event(
                "WARN",
                "redis_get_failed",
                error=str(exc),
            )

    return CACHE.get(
        key
    )


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


task_queue = (
    queue.PriorityQueue()
)


_priority_counter = (
    itertools.count()
)


def submit_task(
    messages,
    priority=5,
    temperature=0.7,
    max_tokens=None,
):

    future = Future()

    tie_breaker = (
        next(
            _priority_counter
        )
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


def register_plugin(
    func,
):

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

        "status":
            "ok",

        "providers":
            {},

        "queue_size":
            task_queue.qsize(),

        "cache_size":
            len(
                CACHE.store
            ),

        "redis_enabled":
            REDIS_ENABLED,
    }

    for provider in (
        PROVIDERS.values()
    ):

        healthy = 0

        total = 0

        for model in (
            provider.models
        ):

            for key in (
                provider.keys
            ):

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

            "healthy":
                healthy,

            "total":
                total,

            "models":
                len(
                    provider.models
                ),
        }

    return result


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

    version="6.0",

    description=(
        "Multi-provider LLM Gateway "
        "com Redis, cache, "
        "dynamic model discovery, "
        "ranking, reasoning prioritization, "
        "circuit breaker, failover, "
        "TPM control e compatibilidade "
        "OpenAI."
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
            for value in
            CONFIG.cors_origins.split(",")
            if value.strip()
        ]
    )

    app.add_middleware(

        CORSMiddleware,

        allow_origins=
            origins,

        allow_credentials=
            True,

        allow_methods=
            ["*"],

        allow_headers=
            ["*"],
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

    token = (

        authorization[
            len("Bearer "):
        ]

        if authorization.startswith(
            "Bearer "
        )

        else ""
    )

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
# SCHEMAS
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


def messages_to_dicts(
    messages,
):

    return [
        message.model_dump()
        for message in messages
    ]


# ============================================================
# /CHAT
# ============================================================

@app.post(
    "/chat",
    dependencies=[
        Depends(
            require_api_key
        )
    ],
)
def chat(
    req: ChatRequest,
):

    try:

        messages = (
            messages_to_dicts(
                req.messages
            )
        )

        future = submit_task(
            messages,

            priority=
                req.priority,

            temperature=
                req.temperature,

            max_tokens=
                req.max_tokens,
        )

        result = future.result(
            timeout=(
                CONFIG.timeout
                * CONFIG.max_attempts
                + 30
            )
        )

        return {
            "response":
                result
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


# ============================================================
# OPENAI COMPATIBLE
# ============================================================

@app.post(
    "/v1/chat/completions",
    dependencies=[
        Depends(
            require_api_key
        )
    ],
)
def openai_chat_completions(
    req: ChatRequest,
):

    request_id = (
        new_request_id()
    )

    try:

        messages = (
            messages_to_dicts(
                req.messages
            )
        )

        result = execute_protected(

            messages,

            temperature=
                req.temperature,

            max_tokens=
                req.max_tokens,
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

        "id":
            f"chatcmpl-{request_id}",

        "object":
            "chat.completion",

        "created":
            int(time.time()),

        "model":
            "gateway",

        "choices": [

            {

                "index":
                    0,

                "message": {

                    "role":
                        "assistant",

                    "content":
                        result,
                },

                "finish_reason":
                    "stop",
            }
        ],

        "usage": {

            "prompt_tokens":
                0,

            "completion_tokens":
                completion_tokens,

            "total_tokens":
                completion_tokens,
        },
    }


# ============================================================
# MODELS
# ============================================================

@app.get(
    "/v1/models"
)
def list_models():

    return {

        "object":
            "list",

        "data": [

            {
                "id":
                    "gateway",

                "object":
                    "model",

                "owned_by":
                    "local",
            }
        ],
    }


# ============================================================
# HEALTH
# ============================================================

@app.get(
    "/health"
)
def health_endpoint():

    return health_status()


# ============================================================
# STATS
# ============================================================

@app.get(
    "/stats"
)
def stats_endpoint():

    return {

        "metrics":
            metrics.snapshot(),

        "timeouts":
            timeout_manager.snapshot(),

        "queue_size":
            task_queue.qsize(),

        "cache_size":
            len(
                CACHE.store
            ),

        "redis_enabled":
            REDIS_ENABLED,

        "config": {

            "max_tokens_hard_cap":
                CONFIG.max_tokens_hard_cap,

            "groq_tpm_budget":
                CONFIG.groq_tpm_budget,

            "groq_tpm_safety_margin":
                CONFIG.groq_tpm_safety_margin,

            "max_attempts":
                CONFIG.max_attempts,

            "dynamic_models":
                CONFIG.dynamic_models,

            "groq_models":
                PROVIDERS[
                    "groq"
                ].models,

            "gemini_models":
                PROVIDERS[
                    "gemini"
                ].models,

            "openrouter_models":
                PROVIDERS[
                    "openrouter"
                ].models,
        },
    }


# ============================================================
# ROOT
# ============================================================

@app.get(
    "/"
)
def root():

    return {

        "service":
            "llm-gateway",

        "status":
            "ok",

        "version":
            "6.0",
    }


# ============================================================
# VALIDATION ERROR
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

        content={
            "error": {

                "message":
                    "Requisição inválida",

                "type":
                    "invalid_request_error",

                "code":
                    "validation_error",

                "details":
                    exc.errors(),
            }
        },
    )


# ============================================================
# GENERIC ERROR
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

        error=str(
            exc
        ),
    )

    return JSONResponse(

        status_code=500,

        content={
            "error": {

                "message":
                    "internal_error",

                "type":
                    "server_error",

                "code":
                    "internal_error",
            }
        },
    )


# ============================================================
# STARTUP
# ============================================================

@app.on_event(
    "startup"
)
async def on_startup():

    refresh_models(
        force=True
    )

    log_event(

        "INFO",

        "gateway_startup",

        version="6.0",

        total_keys=
            _total_keys,

        redis_enabled=
            REDIS_ENABLED,

        dynamic_models=
            CONFIG.dynamic_models,

        groq_models=
            PROVIDERS[
                "groq"
            ].models,

        gemini_models=
            PROVIDERS[
                "gemini"
            ].models,

        openrouter_models=
            PROVIDERS[
                "openrouter"
            ].models,
    )


# ============================================================
# SHUTDOWN
# ============================================================

@app.on_event(
    "shutdown"
)
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

    uvicorn.run(

        app,

        host=os.getenv(
            "GATEWAY_HOST",
            "127.0.0.1",
        ),

        port=int(
            os.getenv(
                "GATEWAY_PORT",
                "8000",
            )
        ),
    )
