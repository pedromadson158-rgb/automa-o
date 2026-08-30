"""
Acesso ao IA Router (llm_gateway) para handlers da infra.
Regra: LLM sempre via Router/Gateway - nunca provider direto.
"""
import sys
from pathlib import Path

_ROUTER_DIR = Path(__file__).resolve().parent.parent / "hermes" / "llm_router"
if str(_ROUTER_DIR) not in sys.path:
    sys.path.insert(0, str(_ROUTER_DIR))

import llm_gateway  # noqa: E402


def complete(prompt, system="", max_tokens=512, temperature=0.7):
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    return llm_gateway.execute_protected(
        messages, temperature=temperature, max_tokens=max_tokens
    )
