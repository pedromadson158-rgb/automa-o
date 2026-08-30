"""
FASE 6.1 - Handler PLAN_CONTENT.
Gera a hipotese do conteudo (experimento) via IA Router e registra em
content.v1. Idempotente por plan_key.
"""
import os
import re
import json
import hashlib
import logging

from mongo_connection import get_client
from content_store import ContentStore
from llm_client import complete

logger = logging.getLogger("plan_handler")

FORMATOS = [
    "achadinhos", "dicas", "listas", "comparacoes", "curiosidades",
    "tendencias", "educativo", "autoridade", "entretenimento",
    "identificacao", "demonstracoes", "prova_social", "produtos", "ofertas",
]


def _parse_json(raw):
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except Exception:
        return json.loads(re.sub(r",\s*([}\]])", r"\1", text))


def handle(task):
    payload = task.get("payload") or {}
    produto = str(payload.get("produto", ""))
    publico = str(payload.get("publico", ""))
    objetivo = str(payload.get("objetivo", "TESTE"))
    posicionamento = str(payload.get("posicionamento", ""))

    plan_key = payload.get("plan_key")
    if not plan_key:
        seed = "|".join([produto, publico, objetivo]).encode("utf-8")
        plan_key = "plan:" + hashlib.sha1(seed).hexdigest()[:12] + ":v1"

    store = ContentStore(get_client()[os.getenv("MONGODB_DATABASE", "automacao")])
    store.ensure_indexes()

    existing = store.find_by_plan_key(plan_key)
    if existing:
        logger.info("content_reused content_id=%s", existing["content_id"])
        return {"content_id": existing["content_id"], "reused": True}

    prompt = (
        "Voce e o Planner de uma maquina de crescimento para Instagram.\n"
        f"Produto: {produto}\nPublico: {publico}\n"
        f"Objetivo declarado: {objetivo}\nPosicionamento: {posicionamento}\n\n"
        "Gere UMA hipotese de conteudo como experimento.\n"
        "formato deve ser um de: " + ", ".join(FORMATOS) + ".\n"
        "JSON: {objetivo, formato, tema, angulo, cta_esperado, sinal_esperado, hipotese}"
    )
    raw = complete(
        prompt,
        system="Retorne APENAS JSON valido. Sem markdown.",
        max_tokens=400,
        temperature=0.7,
    )
    hyp = _parse_json(raw)

    hypothesis = {
        "objetivo": str(hyp.get("objetivo", objetivo)),
        "formato": str(hyp.get("formato", "dicas")),
        "tema": str(hyp.get("tema", produto)),
        "angulo": str(hyp.get("angulo", "")),
        "cta_esperado": str(hyp.get("cta_esperado", "link na bio")),
        "sinal_esperado": str(hyp.get("sinal_esperado", "")),
        "hipotese": str(hyp.get("hipotese", "")),
    }
    doc = store.create(
        hypothesis,
        plan_key=plan_key,
        positioning_ref=posicionamento or None,
    )
    return {"content_id": doc["content_id"], "reused": False}
