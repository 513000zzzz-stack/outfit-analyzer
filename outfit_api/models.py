from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

DEFAULT_BIO = "这个人很懒，什么都没留下"
DEFAULT_AVATAR = ""


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True)
    password_hash: Mapped[str] = mapped_column(String(160))
    bio: Mapped[str] = mapped_column(String(140), default=DEFAULT_BIO)
    avatar: Mapped[str] = mapped_column(String(255), default=DEFAULT_AVATAR)


class Analysis(Base):
    __tablename__ = "analyses"
    # 历史查询按 owner_id 过滤、按 created_at 倒序，复合索引同时覆盖过滤和排序。
    __table_args__ = (Index("ix_analyses_owner_created", "owner_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    filename: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    note: Mapped[str] = mapped_column(Text, default="")
    yolo: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    doubao: Mapped[dict | None] = mapped_column(JSON, nullable=True)
