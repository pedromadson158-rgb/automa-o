import os
import sys
import threading
import logging
from datetime import timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", ".env"
))

logging.basicConfig(level=logging.INFO)

from mongo_connection import get_client
from task_manager import (
    TaskManager, PENDING, PROCESSING, RETRY_WAIT,
    SUCCESS, DEAD_LETTER, CANCELLED, utcnow,
)

def as_utc(dt):
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


client = get_client()
client.admin.command("ping")
print("MONGO OK")

DB_NAME = "automacao_fase1_test"
client.drop_database(DB_NAME)
tm = TaskManager(db=client[DB_NAME])
tm.ensure_indexes()
W = "worker-A"

# 1. CRIACAO
t = tm.create_task(
    "GENERATE_COPY", payload={"produto": "teste"},
    idempotency_key="copy:content_1:v1",
)
assert t["status"] == PENDING and t["attempt"] == 0
print("1 CRIACAO OK")

# 2. IDEMPOTENCIA (criar 2x -> 1 so tarefa)
t2 = tm.create_task("GENERATE_COPY", idempotency_key="copy:content_1:v1")
assert t2["task_id"] == t["task_id"]
assert tm.tasks.count_documents(
    {"idempotency_key": "copy:content_1:v1"}
) == 1
print("2 IDEMPOTENCIA OK")

# 3. ACQUIRE
acq = tm.acquire_task(W)
assert acq["task_id"] == t["task_id"]
assert acq["status"] == PROCESSING and acq["attempt"] == 1
assert acq["lease_until"] is not None
print("3 ACQUIRE OK")

# 4. CONCORRENCIA (5 tarefas, 8 threads, 1 vencedor por tarefa)
for i in range(5):
    tm.create_task("CONC", idempotency_key=f"conc:{i}")
wins = []
lock = threading.Lock()

def worker(wid):
    got = tm.acquire_task(wid)
    if got:
        with lock:
            wins.append((wid, got["task_id"]))

threads = [
    threading.Thread(target=worker, args=(f"w{i}",))
    for i in range(8)
]
for th in threads:
    th.start()
for th in threads:
    th.join()
ids = [tid for _, tid in wins]
assert len(ids) == len(set(ids)), "mesma tarefa adquirida 2x!"
assert len(ids) == 5
print("4 CONCORRENCIA OK (5 tarefas, 8 workers, 0 duplicatas)")

# 5. LEASE (renova dono; intruso eh rejeitado)
assert tm.renew_lease(t["task_id"], W) is not None
assert tm.renew_lease(t["task_id"], "intruso") is None
print("5 LEASE OK")

# 6. COMPLETE (2x completa -> 2a rejeitada)
done = tm.complete_task(t["task_id"], W, result={"copy": "ok"})
assert done["status"] == SUCCESS
assert done["lease_until"] is None and done["worker_id"] is None
assert tm.complete_task(t["task_id"], W) is None
print("6 COMPLETE OK")

# 7. RETRY (falha 1 -> RETRY_WAIT com backoff)
tr = tm.create_task("RETRY", idempotency_key="retry:1")
a = tm.acquire_task(W)
assert a["task_id"] == tr["task_id"]
f = tm.fail_task(tr["task_id"], W, "erro de teste", "generic")
assert f["status"] == RETRY_WAIT
assert as_utc(f["run_after"]) > utcnow()
print("7 RETRY OK")

# 8. LEASE EXPIRADO -> RECUPERACAO
tl = tm.create_task("LEASE", idempotency_key="lease:1")
tm.acquire_task(W)
tm.tasks.update_one(
    {"task_id": tl["task_id"]},
    {"$set": {"lease_until": utcnow() - timedelta(seconds=10)}},
)
rec = tm.recover_expired_tasks()
assert any(r["task_id"] == tl["task_id"] for r in rec)
assert tm.get_task(tl["task_id"])["status"] == RETRY_WAIT
print("8 RECUPERACAO OK")

# 9. DEAD LETTER (falhar ate max_attempts)
td = tm.create_task("DEAD", idempotency_key="dead:1")
for i in range(3):
    tm.tasks.update_one(
        {"task_id": td["task_id"]},
        {"$set": {"run_after": utcnow() - timedelta(seconds=1)}},
    )
    a = tm.acquire_task(W)
    assert a["task_id"] == td["task_id"]
    tm.fail_task(td["task_id"], W, f"falha {i + 1}")
assert tm.get_task(td["task_id"])["status"] == DEAD_LETTER
assert any(
    d["task_id"] == td["task_id"] for d in tm.list_dead_letters()
)
print("9 DEAD LETTER OK")

# 10. RETRY DE DEAD LETTER
r = tm.retry_dead_letter(td["task_id"])
assert r["status"] == PENDING
print("10 RETRY DEAD LETTER OK")

# 11. CANCEL
tc = tm.create_task("CANCEL", idempotency_key="cancel:1")
c = tm.cancel_task(tc["task_id"])
assert c["status"] == CANCELLED
print("11 CANCEL OK")

client.drop_database(DB_NAME)
print("TODOS OS TESTES PASSARAM")
