"""FASE 6.5 - Handler IMAGE_CONTENT."""
import os, sys, logging
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'skills', 'image-engine'))
from mongo_connection import get_client
from content_store import ContentStore
import hermes_image_v20 as img

logger = logging.getLogger("image_handler")

def handle(task):
    payload = task.get("payload") or {}
    content_id = payload.get("content_id")
    store = ContentStore(get_client()[os.getenv("MONGODB_DATABASE", "automacao")])
    content = store.get(content_id)
    if not content:
        raise ValueError(f"content_id {content_id} nao encontrado")
    
    copy_data = ((content.get("steps") or {}).get("COPY") or {}).get("data") or {}
    body = copy_data.get("body", "")
    if not body:
        raise ValueError("sem COPY para gerar imagem")
    
    res = img.run({"copy": body})
    prompt = res.get("prompt_completo", "")
    score = res.get("qualidade", {}).get("score", 0)
    
    image_data = {
        "prompt": prompt,
        "score": score,
        "style": res.get("estilo_nome", ""),
        "approved": res.get("qualidade", {}).get("aprovado", False),
    }
    store.save_step(content_id, "IMAGE", image_data)
    logger.info("image_generated content_id=%s score=%s", content_id, score)
    return {"content_id": content_id, "score": score}
