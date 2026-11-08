import logging
import os
import shutil
from contextlib import asynccontextmanager
from datetime import timezone
from pathlib import PurePosixPath
from typing import Annotated
from uuid import uuid4

import jwt
from fastapi import Depends, FastAPI, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field
from redis import Redis
from rq import Queue
from rq.job import Callback
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from auth import check_password, hash_password, make_token, signing_key, token_user_id
from database import Analysis, Base, User, get_engine, session, storage
from jobs import job_failed, process_analysis

logger = logging.getLogger(__name__)
MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 16_000_000
FILES = {
    "input.jpg": "input.jpg",
    "detection.jpg": "yolo/detection.jpg",
    "overall_palette.png": "yolo/overall_palette.png",
}


@asynccontextmanager
async def lifespan(app):
    signing_key()
    Base.metadata.create_all(get_engine())
    storage().mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="穿搭分析 API", lifespan=lifespan)
bearer = HTTPBearer(auto_error=False)


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(min_length=8, max_length=128)


class Note(BaseModel):
    note: str = Field(max_length=1000)


def current_user(auth: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
    if auth:
        try:
            user_id = token_user_id(auth.credentials)
            with session() as db:
                if db.get(User, user_id):
                    return user_id
        except (jwt.InvalidTokenError, ValueError):
            pass
    raise HTTPException(401, "请重新登录", headers={"WWW-Authenticate": "Bearer"})


Owner = Annotated[int, Depends(current_user)]


def get_owned(db, analysis_id, owner_id):
    row = db.get(Analysis, analysis_id)
    if row is None or row.owner_id != owner_id:
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
    with Redis.from_url(os.environ["REDIS_URL"], socket_connect_timeout=3, socket_timeout=5) as broker:
        Queue("outfit", connection=broker).enqueue(
            process_analysis, analysis_id, job_id=analysis_id,
            job_timeout=600, on_failure=Callback(job_failed),
        )


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


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/auth/register", status_code=201)
def register(data: Credentials):
    with session() as db:
        user = User(username=data.username.lower(), password_hash=hash_password(data.password))
        db.add(user)
        try:
            db.commit()
        except IntegrityError as error:
            raise HTTPException(409, "用户名已被使用") from error
        return {"username": user.username}


@app.post("/auth/login")
def login(data: Credentials):
    with session() as db:
        user = db.scalar(select(User).where(User.username == data.username.lower()))
        if user is None or not check_password(data.password, user.password_hash):
            raise HTTPException(401, "用户名或密码错误")
        return {"access_token": make_token(user.id), "token_type": "bearer"}


@app.post("/analyses", status_code=202)
def submit(image: UploadFile, owner_id: Owner):
    analysis_id = str(uuid4())
    folder = storage() / analysis_id
    folder.mkdir()
    try:
        save_upload(image, folder / "input.jpg")
        filename = PurePosixPath((image.filename or "image").replace("\\", "/")).name[:255]
        with session() as db:
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
        with session() as db:
            db.execute(
                update(Analysis)
                .where(Analysis.id == analysis_id, Analysis.status == "queued")
                .values(status="failed", yolo=detail, doubao=detail)
            )
            db.commit()
    with session() as db:
        return serialize(db.get(Analysis, analysis_id))


@app.get("/analyses")
def list_analyses(owner_id: Owner):
    with session() as db:
        rows = db.scalars(
            select(Analysis).where(Analysis.owner_id == owner_id)
            .order_by(Analysis.created_at.desc()).limit(100)
        )
        return [serialize(row) for row in rows]


@app.get("/analyses/{analysis_id}")
def get_analysis(analysis_id: str, owner_id: Owner):
    with session() as db:
        return serialize(get_owned(db, analysis_id, owner_id))


@app.patch("/analyses/{analysis_id}")
def edit_note(analysis_id: str, note: Note, owner_id: Owner):
    with session() as db:
        row = get_owned(db, analysis_id, owner_id)
        row.note = note.note
        db.commit()
        return serialize(row)


@app.delete("/analyses/{analysis_id}", status_code=204)
def delete_analysis(analysis_id: str, owner_id: Owner):
    with session() as db:
        row = get_owned(db, analysis_id, owner_id)
        if row.status in {"queued", "running"}:
            raise HTTPException(409, "请等待分析结束后再删除")
        db.delete(row)
        db.commit()
    shutil.rmtree(storage() / analysis_id, ignore_errors=True)
    return Response(status_code=204)


@app.get("/analyses/{analysis_id}/files/{name}")
def get_image(analysis_id: str, name: str, owner_id: Owner):
    with session() as db:
        get_owned(db, analysis_id, owner_id)
    relative = FILES.get(name)
    if relative:
        path = storage() / analysis_id / relative
        if path.is_file():
            return FileResponse(path, headers={"Cache-Control": "private, no-store"})
    raise HTTPException(404, "找不到这张结果图片")
