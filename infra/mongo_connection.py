import os
import logging
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

# ============================================================
# ENV - carrega o .env da raiz do projeto (nao depende do CWD)
# ============================================================
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

logger = logging.getLogger("infra.mongo")

_CLIENT = None


def _client_kwargs():
    # Datetimes com fuso UTC, consistentes com utcnow() do Task Manager.
    try:
        from bson.datetime_ms import DatetimeConversion
        return {"datetime_conversion": DatetimeConversion.DATETIME_AWARE}
    except Exception:
        try:
            from pymongo import DatetimeConversion
            return {"datetime_conversion": DatetimeConversion.DATETIME_AWARE}
        except Exception:
            return {}


def get_mongo_uri():
    uri = os.getenv("MONGODB_URI")
    if not uri:
        raise RuntimeError(
            "MONGODB_URI nao configurada. Defina a variavel de ambiente "
            "ou crie um arquivo .env na raiz do projeto com MONGODB_URI=..."
        )
    return uri


def get_client():
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = MongoClient(
            get_mongo_uri(),
            serverSelectionTimeoutMS=10000,
            **_client_kwargs(),
        )
    return _CLIENT


def get_db(name=None):
    return get_client()[name or os.getenv("MONGODB_DATABASE", "automacao")]


def ping():
    get_client().admin.command("ping")
    return True
