"""
FASE 4 - Executor efemero (data plane).

Fluxo: Mongo (verdade) -> acquire atomico -> handler -> complete/fail.
Redis e opcional (acelerador); se cair, o worker segue pelo Mongo.
"""
import os
import sys
import socket
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mongo_connection import get_client
from task_manager import TaskManager
from queue_manager import TaskQueue
import plan_handler
import copy_handler
import image_handler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("worker")

WORKER_ID = os.getenv("WORKER_ID", socket.gethostname())


# ---------------------------------------------------------------
# HANDLERS (data plane). Cada handler recebe a task e retorna dict.
# ---------------------------------------------------------------
def handle_echo(task):
    return {"echo": task.get("payload"), "worker": WORKER_ID}


HANDLERS = {
    "ECHO": handle_echo,
    "PLAN_CONTENT": plan_handler.handle,
    "COPY_CONTENT": copy_handler.handle,
    "IMAGE_CONTENT": image_handler.handle,
}


def run_once():
    mongo = get_client()
    db_name = os.getenv("MONGODB_DATABASE", "automacao")
    tm = TaskManager(db=mongo[db_name])
    q = TaskQueue(task_manager=tm)

    task = tm.acquire_task(WORKER_ID)
    if not task:
        logger.info("no_eligible_task")
        return 0

    task_id = task["task_id"]
    ttype = task["type"]
    handler = HANDLERS.get(ttype)

    if handler is None:
        tm.fail_task(task_id, WORKER_ID,
                     f"no_handler_for_{ttype}", "invalid_request")
        logger.warning("no_handler type=%s task_id=%s", ttype, task_id)
        return 1

    try:
        result = handler(task)
        tm.complete_task(task_id, WORKER_ID, result=result)
        if q.available:
            q.remove(task_id)
        logger.info("task_done task_id=%s type=%s", task_id, ttype)
    except Exception as exc:
        tm.fail_task(task_id, WORKER_ID, str(exc), "handler_error")
        logger.error("task_failed task_id=%s err=%s", task_id, exc)
    return 1


if __name__ == "__main__":
    processed = 0
    for _ in range(int(os.getenv("WORKER_MAX_TASKS", "1"))):
        processed += run_once()
    print(f"WORKER_FINISHED processed={processed}")
