"""FASE 6.10 - Handler METRICS_CONTENT.
Coleta metricas do post publicado (placeholder para Instagram real)."""
import os, sys, logging
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'skills', 'copy-engine'))

from mongo_connection import get_client
from content_store import ContentStore

logger = logging.getLogger("metrics_handler")


def handle(task):
    payload = task.get("payload") or {}
    content_id = payload.get("content_id")
    
    store = ContentStore(get_client()[os.getenv("MONGODB_DATABASE", "automacao")])
    content = store.get(content_id)
    if not content:
        raise ValueError(f"content_id {content_id} nao encontrado")
    
    # Verifica se foi publicado
    publish_data = ((content.get("steps") or {}).get("PUBLISH") or {}).get("data") or {}
    if publish_data.get("status") != "simulated":
        store.save_step(content_id, "METRICS",
                        {"status": "skipped", "reason": "not_published"})
        return {"content_id": content_id, "collected": False}
    
    post_id = publish_data.get("post_id")
    published_at = publish_data.get("published_at")
    
    # Placeholder: metricas zeradas (serao preenchidas quando Instagram real)
    now = datetime.now(timezone.utc)
    hours_since = (now - datetime.fromisoformat(published_at)).total_seconds() / 3600
    
    metrics_data = {
        "post_id": post_id,
        "hours_since_publish": round(hours_since, 1),
        "timeframes": {
            "1h": {"alcance": 0, "engajamento": 0, "salvamentos": 0},
            "6h": {"alcance": 0, "engajamento": 0, "salvamentos": 0},
            "24h": {"alcance": 0, "engajamento": 0, "salvamentos": 0},
            "48h": {"alcance": 0, "engajamento": 0, "salvamentos": 0},
        },
        "classificacao": "PENDENTE",  # VENCEDOR / NORMAL / FRACO / DADOS_INSUFICIENTES
        "collected_at": now.isoformat(),
        "source": "placeholder",  # sera "instagram_graph_api" quando real
    }
    
    store.save_step(content_id, "METRICS", metrics_data)
    logger.info("metrics_collected content_id=%s hours=%.1f", content_id, hours_since)
    return {"content_id": content_id, "collected": True}
