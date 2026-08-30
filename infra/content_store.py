"""
FASE 6 - Content Engine: modelo de dados content.v1 (Mongo = verdade).

Cada conteudo e um experimento com etapas recuperaveis:
PLAN -> RESEARCH -> COPY -> QA -> DECISION -> RENDER -> PUBLISH -> METRICS
"""
import uuid
import logging
from datetime import datetime, timezone

from pymongo import ReturnDocument

logger = logging.getLogger("content_store")

SCHEMA_VERSION = "content.v1"

PIPELINE_STEPS = [
    "PLAN", "RESEARCH", "COPY", "QA",
    "DECISION", "RENDER", "PUBLISH", "METRICS",
]

DECISIONS = ["PUBLICAR", "REFINAR", "DESCARTAR", "HOLD"]


def utcnow():
    return datetime.now(timezone.utc)


class ContentStore:
    def __init__(self, db):
        self.contents = db["contents"]

    def ensure_indexes(self):
        self.contents.create_index("content_id", unique=True)
        self.contents.create_index("plan_key", unique=True, sparse=True)
        self.contents.create_index([("step", 1), ("status", 1)])

    def create(self, hypothesis, plan_key=None, positioning_ref=None):
        now = utcnow()
        doc = {
            "content_id": str(uuid.uuid4()),
            "schema": SCHEMA_VERSION,
            "step": "PLAN",
            "status": "PENDING",
            "positioning_ref": positioning_ref,
            "plan_key": plan_key,
            "hypothesis": hypothesis,
            "steps": {"PLAN": {"at": now, "data": hypothesis}},
            "decision": None,
            "publish": None,
            "metrics": {},
            "learning": {},
            "created_at": now,
            "updated_at": now,
        }
        self.contents.insert_one(doc)
        logger.info("content_created content_id=%s plan_key=%s",
                    doc["content_id"], plan_key)
        return doc

    def get(self, content_id):
        return self.contents.find_one({"content_id": content_id})

    def find_by_plan_key(self, plan_key):
        return self.contents.find_one({"plan_key": plan_key})

    def save_step(self, content_id, step, data):
        now = utcnow()
        return self.contents.find_one_and_update(
            {"content_id": content_id},
            {"$set": {
                "steps." + step: {"at": now, "data": data},
                "step": step,
                "updated_at": now,
            }},
            return_document=ReturnDocument.AFTER,
        )

    def set_decision(self, content_id, decision, reason=None):
        now = utcnow()
        return self.contents.find_one_and_update(
            {"content_id": content_id},
            {"$set": {
                "decision": {"valor": decision, "reason": reason, "at": now},
                "step": "DECISION",
                "updated_at": now,
            }},
            return_document=ReturnDocument.AFTER,
        )
