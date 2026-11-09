import os
from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


@lru_cache
def engine(url):
    return create_engine(url, pool_pre_ping=True, hide_parameters=True)


def get_engine():
    return engine(os.environ["DATABASE_URL"])


def session():
    return Session(get_engine())


def storage():
    return Path(os.environ.get("STORAGE_DIR", "storage")).resolve()


def redis_url():
    return os.environ["REDIS_URL"]
