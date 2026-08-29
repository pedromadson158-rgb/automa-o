import os
import sys
import logging
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", ".env"
))

logging.basicConfig(level=logging.INFO)

import redis as redis_lib

try:
    from task_manager import TaskManager
    from queue_manager import TaskQueue
except ImportError:
    from infra.task_manager import TaskManager
    from infra.queue_manager import TaskQueue

from mongo_connection import get_client

def utcnow():
    return datetime.now(timezone.utc)

client = redis_lib.Redis(
    host="127.0.0.1", port=6379, db=0,
    decode_responses=True, socket_connect_timeout=2,
)
assert client.ping() is True
print("REDIS OK")

mongo = get_client()
DB = "automacao_fase3_test"
mongo.drop_database(DB)
tm = TaskManager(db=mongo[DB])
tm.ensure_indexes()
q = TaskQueue(
    task_manager=tm,
    redis_client=client,
    queue_key="test:tasks:ready",
)

# Limpeza inicial: remove sobras de execucoes anteriores (reprodutibilidade)
q.clear()

# 1. enqueue/dequeue respeita run_after
t1 = tm.create_task("T", idempotency_key="q:1")
t2 = tm.create_task("T", idempotency_key="q:2")
tfut = tm.create_task(
    "T", idempotency_key="q:3",
    run_after=utcnow() + timedelta(seconds=60),
)
q.enqueue(t1["task_id"])
q.enqueue(t2["task_id"])
q.enqueue(tfut["task_id"], run_after=tfut["run_after"])
assert q.size() == 3
g1 = q.dequeue()
g2 = q.dequeue()
assert {g1, g2} == {t1["task_id"], t2["task_id"]}
assert q.dequeue() is None  # futura nao sai
print("1 FILA OK")

# 2. rebuild a partir do Mongo
q.clear()
assert q.size() == 0
n = q.rebuild_from_mongo()
assert n == 3
assert q.dequeue() is not None
print("2 REBUILD OK")

# 3. integracao: dequeue + acquire atomico no Mongo
q.clear()
q.rebuild_from_mongo()
tid = q.dequeue()
acq = tm.acquire_task("worker-q")
assert acq["task_id"] == tid
assert acq["status"] == "PROCESSING"
q.remove(tid)
done = tm.complete_task(tid, "worker-q", result="ok")
assert done["status"] == "SUCCESS"
print("3 INTEGRACAO OK")

# 4. Mongo continua sendo a verdade apos rebuild
n = q.rebuild_from_mongo()
ids = [i for i, _ in q.peek(10)]
assert tid not in ids
assert n == 2
print("4 VERDADE MONGO OK")

mongo.drop_database(DB)
q.clear()
print("TODOS OS TESTES DA FILA PASSARAM")
