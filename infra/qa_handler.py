"""FASE 6.6 - Handler QA_CONTENT (Auto-QA).
Avalia qualidade da copy + imagem e produz decisao preliminar."""
import os, sys, logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'skills', 'copy-engine'))

from mongo_connection import get_client
from content_store import ContentStore
from hermes_v8 import pontuar_copy

logger = logging.getLogger("qa_handler")


def handle(task):
    payload = task.get("payload") or {}
    content_id = payload.get("content_id")
    store = ContentStore(get_client()[os.getenv("MONGODB_DATABASE", "automacao")])
    content = store.get(content_id)
    if not content:
        raise ValueError(f"content_id {content_id} nao encontrado")

    # Avalia COPY
    copy_data = ((content.get("steps") or {}).get("COPY") or {}).get("data") or {}
    body = copy_data.get("body", "")
    copy_score = 0.0
    if body:
        try:
            scores = pontuar_copy(body, None)
            copy_score = float(scores.get("score_final", 0))
        except Exception:
            pass

    # Avalia IMAGE
    image_data = ((content.get("steps") or {}).get("IMAGE") or {}).get("data") or {}
    image_score = image_data.get("score", 0)
    image_approved = image_data.get("approved", False)

    # Decisao preliminar
    if copy_score >= 9.0 and image_approved:
        decisao = "APROVAR"
    elif copy_score >= 7.0 and image_approved:
        decisao = "REFINAR"
    else:
        decisao = "DESCARTAR"

    qa_data = {
        "copy_score": copy_score,
        "image_score": image_score,
        "image_approved": image_approved,
        "decisao_preliminar": decisao,
    }
    store.save_step(content_id, "QA", qa_data)
    logger.info("qa_evaluated content_id=%s copy=%.1f image=%.1f decisao=%s",
                content_id, copy_score, image_score, decisao)
    return {"content_id": content_id, "decisao": decisao}
