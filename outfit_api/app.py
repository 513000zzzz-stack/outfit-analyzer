import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import inspect, text

from outfit_api.auth import signing_key
from outfit_api.common.responses import register_error_handlers
from outfit_api.config import get_engine, session, storage
from outfit_api.crud.analyses import fail_stale
from outfit_api.middleware import RequestLogMiddleware
from outfit_api.models import DEFAULT_AVATAR, DEFAULT_BIO, Base
from outfit_api.routers import accounts, analyses, browser_auth, health

logger = logging.getLogger(__name__)


def ensure_schema(engine):
    """给已存在的表补上新增字段和索引，create_all 不会修改旧表。"""
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    with engine.begin() as connection:
        if "users" in tables:
            columns = {column["name"] for column in inspector.get_columns("users")}
            if "bio" not in columns:
                connection.execute(text(
                    f"ALTER TABLE users ADD COLUMN bio VARCHAR(140) NOT NULL DEFAULT '{DEFAULT_BIO}'"
                ))
            if "avatar" not in columns:
                connection.execute(text(
                    f"ALTER TABLE users ADD COLUMN avatar VARCHAR(255) NOT NULL DEFAULT '{DEFAULT_AVATAR}'"
                ))
        if "analyses" in tables:
            columns = {column["name"] for column in inspector.get_columns("analyses")}
            if "started_at" not in columns:
                column_type = (
                    "TIMESTAMP WITH TIME ZONE" if engine.dialect.name == "postgresql" else "DATETIME"
                )
                connection.execute(text(
                    f"ALTER TABLE analyses ADD COLUMN started_at {column_type}"
                ))
            connection.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_analyses_owner_created "
                "ON analyses (owner_id, created_at)"
            ))


@asynccontextmanager
async def lifespan(app):
    signing_key()
    engine = get_engine()
    Base.metadata.create_all(engine)
    ensure_schema(engine)
    storage().mkdir(parents=True, exist_ok=True)
    with session() as db:
        reaped = fail_stale(db)
    if reaped:
        logger.warning("启动时清理了 %s 条超时任务", reaped)
    yield


def create_app():
    app = FastAPI(title="穿搭分析 API", lifespan=lifespan)
    app.add_middleware(RequestLogMiddleware)
    register_error_handlers(app)
    for module in (health, accounts, browser_auth, analyses):
        app.include_router(module.router)
    return app
