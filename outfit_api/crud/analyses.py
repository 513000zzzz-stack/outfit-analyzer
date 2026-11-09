from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import Session

from outfit_api.models import Analysis

JOB_TIMEOUT_SECONDS = 600
# 超过任务超时仍没有结束，说明执行进程已经不在了；多留一分钟避免误杀收尾中的任务。
RUNNING_STALE = timedelta(seconds=JOB_TIMEOUT_SECONDS + 60)
QUEUED_STALE = timedelta(minutes=30)
STALE_DETAIL = {"status": "error", "error": "任务长时间没有进展，已标记为失败，请重新提交。"}


def find_owned(db: Session, analysis_id: str, owner_id: int):
    row = db.get(Analysis, analysis_id)
    if row is not None and row.owner_id == owner_id:
        return row
    return None


def list_owned(db: Session, owner_id: int, offset: int, limit: int):
    return db.scalars(
        select(Analysis).where(Analysis.owner_id == owner_id)
        .order_by(Analysis.created_at.desc(), Analysis.id.desc())
        .offset(offset).limit(limit)
    )


def count_owned(db: Session, owner_id: int):
    return db.scalar(select(func.count(Analysis.id)).where(Analysis.owner_id == owner_id))


def mark_queue_failed(db: Session, analysis_id: str, detail: dict):
    db.execute(
        update(Analysis)
        .where(Analysis.id == analysis_id, Analysis.status == "queued")
        .values(status="failed", yolo=detail, doubao=detail)
    )


def claim(db: Session, analysis_id: str, *, now: datetime | None = None):
    """认领任务：queued 直接认领，running 只在明显超时后允许重新认领。"""
    now = now or datetime.now(timezone.utc)
    result = db.execute(
        update(Analysis)
        .where(
            Analysis.id == analysis_id,
            or_(
                Analysis.status == "queued",
                and_(
                    Analysis.status == "running",
                    or_(
                        Analysis.started_at.is_(None),
                        Analysis.started_at < now - RUNNING_STALE,
                    ),
                ),
            ),
        )
        .values(status="running", started_at=now)
    )
    db.commit()
    return result.rowcount == 1


def fail_stale(db: Session, *, now: datetime | None = None):
    """把超时的 queued / running 记录落为终态，避免记录永远停在执行中。"""
    now = now or datetime.now(timezone.utc)
    rows = list(
        db.scalars(
            select(Analysis).where(
                or_(
                    and_(Analysis.status == "queued", Analysis.created_at < now - QUEUED_STALE),
                    and_(
                        Analysis.status == "running",
                        or_(
                            Analysis.started_at.is_(None),
                            Analysis.started_at < now - RUNNING_STALE,
                        ),
                    ),
                )
            )
        )
    )
    for row in rows:
        finished = any(
            branch and branch.get("status") == "ok" for branch in (row.yolo, row.doubao)
        )
        row.yolo = row.yolo or STALE_DETAIL
        row.doubao = row.doubao or STALE_DETAIL
        row.status = "partial" if finished else "failed"
    if rows:
        db.commit()
    return len(rows)
