"""
Task Manager - Fundacao operacional sobre MongoDB.

Estados: PENDING -> PROCESSING -> SUCCESS
         PROCESSING -> RETRY_WAIT -> (PENDING elegivel) 
         PROCESSING -> DEAD_LETTER
         PENDING/RETRY_WAIT -> CANCELLED

MongoDB = verdade. Redis (fase 3) sera apenas aceleracao.
"""
import os
import uuid
import logging
from datetime import datetime, timezone, timedelta

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

try:
    from mongo_connection import get_db
except ImportError:  # quando importado como pacote
    from infra.mongo_connection import get_db

logger = logging.getLogger("task_manager")

# ------------------------------------------------------------
# CONSTANTES
# ------------------------------------------------------------
PENDING = "PENDING"
PROCESSING = "PROCESSING"
RETRY_WAIT = "RETRY_WAIT"
SUCCESS = "SUCCESS"
DEAD_LETTER = "DEAD_LETTER"
CANCELLED = "CANCELLED"

DEFAULT_LEASE_SECONDS = 600          # 10 minutos
BACKOFF_SCHEDULE = [30, 120, 600]    # attempt 1 -> 30s, 2 -> 2min, 3+ -> 10min


def utcnow():
    return datetime.now(timezone.utc)


def _backoff_seconds(attempt):
    idx = min(max(attempt - 1, 0), len(BACKOFF_SCHEDULE) - 1)
    return BACKOFF_SCHEDULE[idx]


class TaskManager:
    def __init__(self, db=None):
        self.db = db if db is not None else get_db()
        self.tasks = self.db[
            os.getenv("MONGODB_TASKS_COLLECTION", "tasks")
        ]

    # --------------------------------------------------------
    # SETUP
    # --------------------------------------------------------
    def ensure_indexes(self):
        self.tasks.create_index("task_id", unique=True)
        self.tasks.create_index(
            "idempotency_key", unique=True, sparse=True
        )
        self.tasks.create_index(
            [("status", 1), ("run_after", 1),
             ("priority", -1), ("created_at", 1)]
        )
        self.tasks.create_index([("status", 1), ("lease_until", 1)])
        self.tasks.create_index("created_at")

    # --------------------------------------------------------
    # CREATE (idempotente e seguro contra corrida)
    # --------------------------------------------------------
    def create_task(
        self,
        type,
        payload=None,
        content_id=None,
        lead_id=None,
        campaign_id=None,
        idempotency_key=None,
        priority=5,
        max_attempts=3,
        run_after=None,
    ):
        now = utcnow()
        if idempotency_key:
            existing = self.tasks.find_one(
                {"idempotency_key": idempotency_key}
            )
            if existing:
                logger.info(
                    "task_create_skipped_idempotent key=%s task_id=%s",
                    idempotency_key, existing["task_id"],
                )
                return existing

        task = {
            "task_id": str(uuid.uuid4()),
            "type": type,
            "status": PENDING,
            "priority": priority,
            "content_id": content_id,
            "lead_id": lead_id,
            "campaign_id": campaign_id,
            "payload": payload or {},
            "attempt": 0,
            "max_attempts": max_attempts,
            "run_after": run_after or now,
            "lease_until": None,
            "worker_id": None,
            "idempotency_key": idempotency_key,
            "last_error": None,
            "last_error_type": None,
            "result": None,
            "created_at": now,
            "updated_at": now,
            "started_at": None,
            "completed_at": None,
        }
        try:
            self.tasks.insert_one(task)
        except DuplicateKeyError:
            existing = self.tasks.find_one(
                {"idempotency_key": idempotency_key}
            )
            if existing:
                return existing
            raise
        logger.info("task_created task_id=%s type=%s", task["task_id"], type)
        return task

    # --------------------------------------------------------
    # READ
    # --------------------------------------------------------
    def get_task(self, task_id):
        return self.tasks.find_one({"task_id": task_id})

    # --------------------------------------------------------
    # ACQUIRE (atomico: apenas 1 worker vence)
    # --------------------------------------------------------
    def acquire_task(self, worker_id, lease_seconds=DEFAULT_LEASE_SECONDS):
        now = utcnow()
        updated = self.tasks.find_one_and_update(
            {
                "status": {"$in": [PENDING, RETRY_WAIT]},
                "run_after": {"$lte": now},
            },
            {
                "$set": {
                    "status": PROCESSING,
                    "worker_id": worker_id,
                    "lease_until": now + timedelta(seconds=lease_seconds),
                    "started_at": now,
                    "updated_at": now,
                },
                "$inc": {"attempt": 1},
            },
            sort=[("priority", -1), ("run_after", 1), ("created_at", 1)],
            return_document=ReturnDocument.AFTER,
        )
        if updated:
            logger.info(
                "task_acquired task_id=%s worker=%s attempt=%s",
                updated["task_id"], worker_id, updated["attempt"],
            )
        return updated

    # --------------------------------------------------------
    # LEASE
    # --------------------------------------------------------
    def renew_lease(self, task_id, worker_id,
                    lease_seconds=DEFAULT_LEASE_SECONDS):
        now = utcnow()
        updated = self.tasks.find_one_and_update(
            {"task_id": task_id, "status": PROCESSING,
             "worker_id": worker_id},
            {"$set": {
                "lease_until": now + timedelta(seconds=lease_seconds),
                "updated_at": now,
            }},
            return_document=ReturnDocument.AFTER,
        )
        if updated:
            logger.info("lease_renewed task_id=%s worker=%s",
                        task_id, worker_id)
        else:
            logger.warning("lease_renew_rejected task_id=%s worker=%s",
                           task_id, worker_id)
        return updated

    def recover_expired_tasks(self):
        now = utcnow()
        expired = list(self.tasks.find(
            {"status": PROCESSING, "lease_until": {"$lt": now}}
        ))
        recovered = []
        for task in expired:
            attempt = task.get("attempt", 1)
            max_attempts = task.get("max_attempts", 3)
            if attempt < max_attempts:
                new_status = RETRY_WAIT
                extra = {"run_after": now}
            else:
                new_status = DEAD_LETTER
                extra = {}
            updated = self.tasks.find_one_and_update(
                {"_id": task["_id"], "status": PROCESSING},
                {"$set": dict(
                    {"status": new_status, "worker_id": None,
                     "lease_until": None, "updated_at": now},
                    **extra,
                )},
                return_document=ReturnDocument.AFTER,
            )
            if updated:
                recovered.append(updated)
                logger.info(
                    "task_recovered task_id=%s new_status=%s",
                    updated["task_id"], new_status,
                )
        return recovered

    # --------------------------------------------------------
    # COMPLETION
    # --------------------------------------------------------
    def complete_task(self, task_id, worker_id, result=None):
        now = utcnow()
        sets = {
            "status": SUCCESS,
            "lease_until": None,
            "worker_id": None,
            "completed_at": now,
            "updated_at": now,
        }
        if result is not None:
            sets["result"] = result
        updated = self.tasks.find_one_and_update(
            {"task_id": task_id, "status": PROCESSING,
             "worker_id": worker_id},
            {"$set": sets},
            return_document=ReturnDocument.AFTER,
        )
        if updated:
            logger.info("task_completed task_id=%s worker=%s",
                        task_id, worker_id)
        else:
            logger.warning("task_complete_rejected task_id=%s worker=%s",
                           task_id, worker_id)
        return updated

    # --------------------------------------------------------
    # FAILURE
    # --------------------------------------------------------
    def fail_task(self, task_id, worker_id, error, error_type=None):
        now = utcnow()
        task = self.get_task(task_id)
        if (
            not task
            or task["status"] != PROCESSING
            or task.get("worker_id") != worker_id
        ):
            logger.warning("task_fail_rejected task_id=%s worker=%s",
                           task_id, worker_id)
            return None

        attempt = task.get("attempt", 1)
        max_attempts = task.get("max_attempts", 3)
        sets = {
            "last_error": str(error),
            "last_error_type": error_type,
            "lease_until": None,
            "worker_id": None,
            "updated_at": now,
        }
        if attempt < max_attempts:
            delay = _backoff_seconds(attempt)
            sets["status"] = RETRY_WAIT
            sets["run_after"] = now + timedelta(seconds=delay)
            logger.info(
                "task_retry_scheduled task_id=%s attempt=%s delay=%ss",
                task_id, attempt, delay,
            )
        else:
            sets["status"] = DEAD_LETTER
            logger.info("task_dead_lettered task_id=%s attempt=%s",
                        task_id, attempt)

        return self.tasks.find_one_and_update(
            {"task_id": task_id, "status": PROCESSING,
             "worker_id": worker_id},
            {"$set": sets},
            return_document=ReturnDocument.AFTER,
        )

    # --------------------------------------------------------
    # DEAD LETTER / CANCEL
    # --------------------------------------------------------
    def list_dead_letters(self, limit=50):
        return list(
            self.tasks.find({"status": DEAD_LETTER})
            .sort("updated_at", -1).limit(limit)
        )

    def retry_dead_letter(self, task_id):
        now = utcnow()
        updated = self.tasks.find_one_and_update(
            {"task_id": task_id, "status": DEAD_LETTER},
            {"$set": {
                "status": PENDING,
                "run_after": now,
                "lease_until": None,
                "worker_id": None,
                "last_error": None,
                "last_error_type": None,
                "updated_at": now,
            }},
            return_document=ReturnDocument.AFTER,
        )
        if updated:
            logger.info("task_dead_letter_retried task_id=%s", task_id)
        return updated

    def cancel_task(self, task_id):
        now = utcnow()
        updated = self.tasks.find_one_and_update(
            {"task_id": task_id,
             "status": {"$in": [PENDING, RETRY_WAIT]}},
            {"$set": {"status": CANCELLED, "updated_at": now}},
            return_document=ReturnDocument.AFTER,
        )
        if updated:
            logger.info("task_cancelled task_id=%s", task_id)
        return updated
