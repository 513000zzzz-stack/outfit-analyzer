from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse

from outfit_api.common.responses import OWNED_RECORD_ERRORS, UNAUTHORIZED, ok
from outfit_api.dependencies import DbSession, Owner
from outfit_api.schemas import (
    AnalysisRecord, ApiResponse, ErrorResponse, HistoryPage, Note,
)
from outfit_api.services import analyses

router = APIRouter(prefix="/api/analysis", tags=["穿搭分析"])


@router.post(
    "/create",
    tags=["穿搭分析"],
    status_code=202,
    summary="上传图片并创建分析任务",
    response_model=ApiResponse[AnalysisRecord],
    response_model_exclude_unset=True,
    responses={
        **UNAUTHORIZED,
        413: {"model": ErrorResponse, "description": "文件大小或图片像素数超限"},
        415: {"model": ErrorResponse, "description": "图片格式不支持或无法解码"},
    },
)
def submit(image: UploadFile, owner_id: Owner, db: DbSession):
    return ok(analyses.create_analysis(db, image, owner_id), "任务已创建", code=202)


@router.get(
    "/list",
    summary="按页读取个人分析历史",
    response_model=ApiResponse[HistoryPage],
    response_model_exclude_unset=True,
    responses=UNAUTHORIZED,
)
def list_analyses(
    owner_id: Owner,
    db: DbSession,
    page: Annotated[int, Query(ge=1, le=1_000_000, description="页码，从 1 开始")] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100, description="每页条数")] = 20,
):
    return ok(analyses.read_history_page(db, owner_id, page, page_size))


@router.get(
    "/detail/{analysis_id}",
    summary="查看任务进度和双方案结果",
    response_model=ApiResponse[AnalysisRecord],
    response_model_exclude_unset=True,
    responses=OWNED_RECORD_ERRORS,
)
def get_analysis(analysis_id: str, owner_id: Owner, db: DbSession):
    return ok(analyses.read_analysis(db, analysis_id, owner_id))


@router.put(
    "/note/{analysis_id}",
    summary="修改分析备注",
    response_model=ApiResponse[AnalysisRecord],
    response_model_exclude_unset=True,
    responses=OWNED_RECORD_ERRORS,
)
def edit_note(analysis_id: str, note: Note, owner_id: Owner, db: DbSession):
    return ok(analyses.change_note(db, analysis_id, owner_id, note.note), "备注已保存")


@router.delete(
    "/delete/{analysis_id}",
    summary="删除已结束的分析",
    response_model=ApiResponse[dict],
    responses={
        **OWNED_RECORD_ERRORS,
        409: {"model": ErrorResponse, "description": "任务仍在排队或运行"},
    },
)
def delete_analysis(analysis_id: str, owner_id: Owner, db: DbSession):
    analyses.remove_analysis(db, analysis_id, owner_id)
    return ok(None, "删除成功")


@router.get(
    "/file/{analysis_id}/{name}",
    summary="读取本人分析记录的图片或文字报告",
    response_class=Response,
    responses={
        **OWNED_RECORD_ERRORS,
        200: {
            "description": "结果图片或 YOLO 文字报告",
            "content": {
                "image/jpeg": {"schema": {"type": "string", "format": "binary"}},
                "image/png": {"schema": {"type": "string", "format": "binary"}},
                "text/plain": {"schema": {"type": "string"}},
            },
        },
    },
)
def get_file(analysis_id: str, name: str, owner_id: Owner, db: DbSession):
    path = analyses.get_file_path(db, analysis_id, name, owner_id)
    headers = {"Cache-Control": "private, no-store"}
    if name == "analysis.txt":
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError as error:
            raise HTTPException(404, "找不到这个分析附件") from error
        # 本地报告包含容器内原图路径，网页已有原图入口。
        report = "\n".join(line for line in lines if not line.startswith("原图："))
        return PlainTextResponse(report, headers=headers)
    return FileResponse(path, headers=headers)
