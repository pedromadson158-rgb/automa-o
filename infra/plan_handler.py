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
    """Parser tolerante: strip reasoning tags, reparos, fecha chaves."""
    import ast
    text = raw.strip()
    # remove blocos <think>...</think> (Qwen e modelos reasoning)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    # se sobrou <think> sem fechamento e nao ha JSON depois, descarta o reasoning
    if "<think>" in text and "{" not in text.split("<think>", 1)[1]:
        text = text.split("<think>", 1)[0].strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    # procura bloco JSON (com ou sem truncamento)
    m = re.search(r"\{.*", text, re.S)
    block = m.group(0) if m else text
    # remove virgulas finais
    block = re.sub(r",\s*([}\]])", r"\1", block)
    # aspas em chaves sem aspas
    block = re.sub(r"([{,]\s*)([A-Za-z_][A-Za-z0-9_\-\s]*?)\s*:",
                   r'\1"\2":', block)
    # tenta parsear; se truncado, fecha chaves/colchetes
    for candidate in (block,):
        try:
            return json.loads(candidate)
        except Exception:
            pass
        # balanceamento: conta { [ vs } ]
        opens = candidate.count("{") + candidate.count("[")
        closes = candidate.count("}") + candidate.count("]")
        trail = candidate.rstrip()
        # fecha string aberta?
        if trail.count('"') % 2 == 1:
            trail += '"'
        # remove ultima virgula solta
        trail = re.sub(r",\s*$", "", trail)
        # adiciona chaves faltantes
        extra = []
        diff_b = candidate.count("{") - candidate.count("}")
        diff_a = candidate.count("[") - candidate.count("]")
        extra.append("}" * max(diff_b, 0))
        extra.append("]" * max(diff_a, 0))
        fixed = trail + "".join(extra)
        try:
            return json.loads(fixed)
        except Exception:
            pass
    # fallback: literal_eval
    try:
        val = ast.literal_eval(block)
        if isinstance(val, dict):
            return val
    except Exception:
        pass
    raise ValueError("hipotese sem JSON valido: " + text[:300])




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
        system="Retorne APENAS JSON valido. Sem markdown. NAO gere blocos de pensamento. NAO use tags <think>. Seja direto.",
        max_tokens=2000,
        temperature=0.3,
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
