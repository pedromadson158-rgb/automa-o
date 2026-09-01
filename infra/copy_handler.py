"""
FASE 6.4 - Handler COPY_CONTENT.
Executa o pipeline de 14 fases do Hermes v8 e salva na etapa COPY.
ADR-017: o LLM do v8 NUNCA chama provider direto - vai pelo IA Router.
"""
import os
import sys
import logging

# garante que o init do LLMClient nao quebra por falta da key Anthropic
os.environ.setdefault("ANTHROPIC_API_KEY", "via-ia-router")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'skills', 'copy-engine'))

from mongo_connection import get_client
from content_store import ContentStore
from llm_client import complete as router_complete
import hermes_v8

logger = logging.getLogger("copy_handler")


def _completar_via_router(self, prompt, system="", max_tokens=1200, **kw):
    """Adapter ADR-017: todo LLM do v8 passa pelo IA Router."""
    import time
    # 1) max_tokens minimo 800 (fases do v8 precisam de output generoso)
    # 2) salt unico por chamada para desabilitar cache do Router
    #    (o v8 ja tem seu proprio cache de fases - cache duplo confunde retry)
    salt = f"\n<!-- r:{int(time.time()*1000000)} -->"
    return router_complete(
        str(prompt) + salt,
        system=str(system or ""),
        max_tokens=max(800, int(max_tokens or 1200)),
        temperature=0.7,
    )


hermes_v8.LLMClient.completar = _completar_via_router

from hermes_v8 import gerar_campanha  # noqa: E402


def handle(task):
    payload = task.get("payload") or {}
    content_id = payload.get("content_id")
    if not content_id:
        raise ValueError("payload sem content_id")

    store = ContentStore(get_client()[os.getenv("MONGODB_DATABASE", "automacao")])
    content = store.get(content_id)
    if not content:
        raise ValueError(f"content_id {content_id} nao encontrado")

    if content.get("steps", {}).get("COPY"):
        logger.info("copy_skipped content_id=%s (ja existe)", content_id)
        return {"content_id": content_id, "skipped": True}

    hyp = content.get("hypothesis", {})
    produto_input = {
        "produto_id": content_id,
        "nome": hyp.get("tema", "Produto"),
        "categoria": "geral",
        "preco": "0",
        "publico_alvo": content.get("positioning_ref", ""),
        "dor_principal": hyp.get("angulo", ""),
        "desejo_principal": hyp.get("objetivo", ""),
        "mecanismo_unico": hyp.get("hipotese", ""),
    }

    modo = payload.get("modo", "rapido")
    variacoes = int(payload.get("variacoes", 1))

    resultado = gerar_campanha(
        produto_input,
        cta="link na bio",
        variacoes=variacoes,
        intensidade="agressivo",
        modo=modo,
        salvar=False,
    )

    # extracao defensiva (criativos pode variar entre versoes)
    criativos = resultado.get("criativos") or resultado.get("variacoes") or {}
    post = criativos.get("POST") or criativos.get("posts") or {}
    if isinstance(post, list):
        post = post[0] if post else {}
    texto = post.get("texto") or post.get("copy") or ""
    if not texto:
        raise ValueError("nenhum criativo POST gerado")

    copy_data = {
        "headline": resultado.get("headline") or post.get("headline", ""),
        "body": texto,
        "cta": post.get("cta", "link na bio"),
        "score": post.get("score", (resultado.get("metricas") or {}).get("score_medio", 0)),
        "angulo": post.get("angulo", ""),
        "formato": "POST",
        "modo": modo,
    }
    store.save_step(content_id, "COPY", copy_data)
    logger.info("copy_generated content_id=%s score=%s", content_id, copy_data["score"])
    return {"content_id": content_id, "score": copy_data["score"]}
