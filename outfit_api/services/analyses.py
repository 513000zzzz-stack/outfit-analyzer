import logging
import shutil
from datetime import timezone
from pathlib import PurePosixPath
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from redis import Redis
from rq import Queue
from rq.job import Callback
from sqlalchemy.orm import Session

from jobs import job_failed, process_analysis
from outfit_api.config import redis_url, storage
from outfit_api.crud.analyses import (
    JOB_TIMEOUT_SECONDS, count_owned, find_owned, list_owned, mark_queue_failed,
)
from outfit_api.models import Analysis

logger = logging.getLogger(__name__)
MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 16_000_000
FILES = {
    "input.jpg": "input.jpg",
    "detection.jpg": "yolo/detection.jpg",
    "overall_palette.png": "yolo/overall_palette.png",
    "analysis.txt": "yolo/analysis.txt",
}


def get_owned(db, analysis_id, owner_id):
    row = find_owned(db, analysis_id, owner_id)
    if row is None:
        raise HTTPException(404, "找不到这条分析记录")
    return row


def serialize(row):
    timestamp = row.created_at
    return {
        "id": row.id,
        "filename": row.filename,
        "created_at": (timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=timezone.utc)).isoformat(),
        "status": row.status,
        "note": row.note,
        "yolo": row.yolo,
        "doubao": row.doubao,
    }


def enqueue(analysis_id):
    with Redis.from_url(redis_url(), socket_connect_timeout=3, socket_timeout=5) as broker:
        Queue("outfit", connection=broker).enqueue(
            process_analysis, analysis_id, job_id=analysis_id,
            job_timeout=JOB_TIMEOUT_SECONDS, on_failure=Callback(job_failed),
        )
    # 任务编号同时是 RQ job id，Worker 日志里会打印同一个值，便于对照。
    logger.info("任务 %s 已入队", analysis_id)


def save_upload(image, target):
    image.file.seek(0, 2)
    if image.file.tell() > MAX_BYTES:
        raise HTTPException(413, "图片大小最多为 10 MB")
    image.file.seek(0)
    try:
        with Image.open(image.file, formats=["JPEG", "PNG", "WEBP"]) as picture:
            if picture.width * picture.height > MAX_PIXELS:
                raise HTTPException(413, "图片最多为 1600 万像素")
            corrected = ImageOps.exif_transpose(picture).convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise HTTPException(415, "请选择可读取的 JPEG、PNG 或 WebP 图片") from error
    corrected.save(target, "JPEG", quality=95)


def create_analysis(db: Session, image: UploadFile, owner_id: int):
    analysis_id = str(uuid4())
    folder = storage() / analysis_id
    folder.mkdir(parents=True, exist_ok=True)
    try:
        save_upload(image, folder / "input.jpg")
        filename = PurePosixPath((image.filename or "image").replace("\\", "/")).name[:255] or "image"
        db.add(Analysis(id=analysis_id, owner_id=owner_id, filename=filename))
        db.commit()
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise

    try:
        enqueue(analysis_id)
    except Exception:
        logger.exception("任务 %s 入队失败", analysis_id)
        detail = {"status": "error", "error": "任务队列暂不可用，请重新提交。"}
        mark_queue_failed(db, analysis_id, detail)
        db.commit()
    return serialize(db.get(Analysis, analysis_id))


def read_history(db: Session, owner_id: int, offset: int, limit: int):
    return [serialize(row) for row in list_owned(db, owner_id, offset, limit)]


def read_history_page(db: Session, owner_id: int, page: int, page_size: int):
    offset = (page - 1) * page_size
    batch = read_history(db, owner_id, offset, page_size + 1)
    return {
        "list": batch[:page_size],
        "total": count_owned(db, owner_id),
        "hasMore": len(batch) > page_size,
    }


def read_analysis(db: Session, analysis_id: str, owner_id: int):
    return serialize(get_owned(db, analysis_id, owner_id))


def change_note(db: Session, analysis_id: str, owner_id: int, note: str):
    row = get_owned(db, analysis_id, owner_id)
    row.note = note
    db.commit()
    return serialize(row)


def remove_analysis(db: Session, analysis_id: str, owner_id: int):
    row = get_owned(db, analysis_id, owner_id)
    if row.status in {"queued", "running"}:
        raise HTTPException(409, "请等待分析结束后再删除")
    db.delete(row)
    db.commit()
    shutil.rmtree(storage() / analysis_id, ignore_errors=True)


def get_file_path(db: Session, analysis_id: str, name: str, owner_id: int):
    get_owned(db, analysis_id, owner_id)
    relative = FILES.get(name)
    if relative:
        path = storage() / analysis_id / relative
        if path.is_file():
            return path
    raise HTTPException(404, "找不到这个分析附件")
