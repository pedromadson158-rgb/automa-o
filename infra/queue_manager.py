"""
FASE 3 - Redis como fila rapida de tarefas prontas.

Constituicao:
- Redis = velocidade (atalho para tarefas prontas)
- MongoDB = verdade (estado e aquisicao atomica)
- Se o Redis cair, a fila e reconstruida do Mongo.

A fila NAO executa nada: quem pega tarefa deve sempre confirmar
no Mongo via acquire_task (gate atomico).
"""
import os
import time
import logging
from datetime import datetime, timezone

import redis

try:
    from task_manager import TaskManager, PENDING, RETRY_WAIT
except ImportError:
    from infra.task_manager import TaskManager, PENDING, RETRY_WAIT

logger = logging.getLogger("queue_manager")


def _to_ts(value):
    if value is None:
        return time.time()
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.timestamp()
    return float(value)


class TaskQueue:
    def __init__(
        self,
        task_manager=None,
        redis_client=None,
        queue_key=None,
    ):
        self.tm = task_manager or TaskManager()
        self.queue_key = queue_key or os.getenv(
            "TASK_QUEUE_KEY", "tasks:ready"
        )
        self.redis = redis_client
        if self.redis is None:
            self.redis = self._default_redis()

    def _default_redis(self):
        try:
            client = redis.Redis(
                host=os.getenv("REDIS_HOST", "127.0.0.1"),
                port=int(os.getenv("REDIS_PORT", "6379")),
                db=0,
                decode_responses=True,
                socket_connect_timeout=1,
                socket_timeout=1,
            )
            client.ping()
            return client
        except Exception as exc:
            logger.warning("queue_redis_disabled error=%s", exc)
            return None

    @property
    def available(self):
        return self.redis is not None

    def enqueue(self, task_id, run_after=None):
        if not self.available:
            return False
        self.redis.zadd(
            self.queue_key, {task_id: _to_ts(run_after)}
        )
        return True

    def dequeue(self):
        """Retira a tarefa pronta mais antiga. Retorna task_id ou None."""
        if not self.available:
            return None
        ids = self.redis.zrangebyscore(
            self.queue_key, "-inf", time.time(), start=0, num=1
        )
        if not ids:
            return None
        task_id = ids[0]
        if not self.redis.zrem(self.queue_key, task_id):
            return None
        return task_id

    def peek(self, count=10):
        if not self.available:
            return []
        return self.redis.zrange(
            self.queue_key, 0, count - 1, withscores=True
        )

    def size(self):
        if not self.available:
            return 0
        return self.redis.zcard(self.queue_key)

    def remove(self, task_id):
        if not self.available:
            return False
        return bool(self.redis.zrem(self.queue_key, task_id))

    def clear(self):
        if not self.available:
            return False
        return bool(self.redis.delete(self.queue_key))

    def rebuild_from_mongo(self):
        """Reconstrói a fila Redis a partir do Mongo (fonte da verdade)."""
        if not self.available:
            return 0
        self.clear()
        cursor = self.tm.tasks.find(
            {"status": {"$in": [PENDING, RETRY_WAIT]}},
            {"task_id": 1, "run_after": 1},
        )
        count = 0
        for task in cursor:
            self.redis.zadd(
                self.queue_key,
                {task["task_id"]: _to_ts(task.get("run_after"))},
            )
            count += 1
        logger.info("queue_rebuilt count=%d", count)
        return count
