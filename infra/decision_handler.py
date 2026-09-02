"""FASE 6.7 - Handler DECISION_CONTENT.
Concretiza a decisao do QA e registra oficialmente no content."""
import os, sys, logging
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'skills', 'copy-engine'))

from mongo_connection import get_client
from content_store import ContentStore

logger = logging.getLogger("decision_handler")


def handle(task):
    payload = task.get("payload") or {}
    content_id = payload.get("content_id")
    override = payload.get("override")  # opcional: forçar decisao manualmente
    
    store = ContentStore(get_client()[os.getenv("MONGODB_DATABASE", "automacao")])
    content = store.get(content_id)
    if not content:
        raise ValueError(f"content_id {content_id} nao encontrado")
    
    qa_data = ((content.get("steps") or {}).get("QA") or {}).get("data") or {}
    decisao_preliminar = qa_data.get("decisao_preliminar", "DESCARTAR")
    
    # Override manual tem prioridade
    decisao_final = override if override else decisao_preliminar
    
    # Calcula confianca baseada nos scores
    copy_score = qa_data.get("copy_score", 0)
    image_score = qa_data.get("image_score", 0)
    confianca = min(1.0, (copy_score + image_score) / 20.0)
    
    decision_data = {
        "decisao": decisao_final,
        "decisao_preliminar": decisao_preliminar,
        "override_aplicado": bool(override),
        "confianca": round(confianca, 2),
        "copy_score": copy_score,
        "image_score": image_score,
        "motivo": f"Copy {copy_score}/10 + Image {image_score}/10 → {decisao_final}",
    }
    
    store.save_step(content_id, "DECISION", decision_data)
    logger.info("decision_made content_id=%s decisao=%s confianca=%.2f",
                content_id, decisao_final, confianca)
    return {"content_id": content_id, "decisao": decisao_final}
