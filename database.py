import os
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True)
    password_hash: Mapped[str] = mapped_column(String(160))


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    status: Mapped[str] = mapped_column(String(16), default="queued")
    note: Mapped[str] = mapped_column(Text, default="")
    yolo: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    doubao: Mapped[dict | None] = mapped_column(JSON, nullable=True)


@lru_cache
def engine(url):
    return create_engine(url, pool_pre_ping=True)


def get_engine():
    return engine(os.environ["DATABASE_URL"])


def session():
    return Session(get_engine())


def storage():
    return Path(os.environ.get("STORAGE_DIR", "storage")).resolve()
