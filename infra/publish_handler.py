"""FASE 6.9 - Handler PUBLISH_CONTENT.
Publica a arte renderizada no Instagram (ou simula se sem credenciais)."""
import os, sys, logging
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'skills', 'copy-engine'))

from mongo_connection import get_client
from content_store import ContentStore

logger = logging.getLogger("publish_handler")


def handle(task):
    payload = task.get("payload") or {}
    content_id = payload.get("content_id")
    dry_run = payload.get("dry_run", True)  # True = simula, False = Instagram real
    
    store = ContentStore(get_client()[os.getenv("MONGODB_DATABASE", "automacao")])
    content = store.get(content_id)
    if not content:
        raise ValueError(f"content_id {content_id} nao encontrado")
    
    # Verifica se DECISION é APROVAR
    decision = ((content.get("steps") or {}).get("DECISION") or {}).get("data") or {}
    if decision.get("decisao") != "APROVAR":
        store.save_step(content_id, "PUBLISH",
                        {"status": "skipped_by_decision", "decisao": decision.get("decisao")})
        return {"content_id": content_id, "published": False}
    
    # Extrai dados necessários
    copy_data = ((content.get("steps") or {}).get("COPY") or {}).get("data") or {}
    render_data = ((content.get("steps") or {}).get("RENDER") or {}).get("data") or {}
    
    caption = copy_data.get("body", "")
    image_path = render_data.get("png_path")
    
    if not image_path or not os.path.exists(image_path):
        raise ValueError("PNG nao encontrado para publicacao")
    
    # Simulação de publicação (dry_run=True)
    if dry_run:
        publish_result = {
            "status": "simulated",
            "platform": "instagram",
            "caption_length": len(caption),
            "image_path": image_path,
            "image_size_kb": os.path.getsize(image_path) // 1024,
            "published_at": datetime.now(timezone.utc).isoformat(),
            "post_id": f"sim_{content_id[:8]}",
        }
        logger.info("publish_simulated content_id=%s", content_id)
    else:
        # TODO: integração real com Instagram Graph API
        # Requer: INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_USER_ID
        raise NotImplementedError("Instagram real ainda nao implementado")
    
    store.save_step(content_id, "PUBLISH", publish_result)
    return {"content_id": content_id, "published": True, "post_id": publish_result.get("post_id")}
