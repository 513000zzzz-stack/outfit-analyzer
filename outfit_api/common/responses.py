"""统一响应结构与异常处理。

JSON 接口统一返回 ``{"code": ..., "message": ..., "data": ...}``；
浏览器会话接口返回 HTML 或重定向，不受此结构影响。
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException

from outfit_api.schemas import ErrorResponse

logger = logging.getLogger(__name__)

ENVELOPE_PREFIX = "/api/"

UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "登录凭证无效或已过期"}}
OWNED_RECORD_ERRORS = {
    **UNAUTHORIZED,
    404: {"model": ErrorResponse, "description": "记录不存在或不属于当前用户"},
}


def ok(data=None, message: str = "success", code: int = 200):
    """构造成功响应体，code 与 HTTP 状态码保持一致。"""
    return {"code": code, "message": message, "data": data}


def error_body(code: int, message: str, data=None):
    return {"code": code, "message": message, "data": data}


def uses_envelope(request: Request) -> bool:
    """只有 /api/ 下的 JSON 接口使用统一结构，浏览器表单接口保持 HTML/重定向。"""
    return request.url.path.startswith(ENVELOPE_PREFIX)


def register_error_handlers(app: FastAPI):
    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException):
        if not uses_envelope(request):
            return await http_exception_handler(request, error)
        return JSONResponse(
            status_code=error.status_code,
            content=error_body(error.status_code, str(error.detail)),
            headers=error.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        if not uses_envelope(request):
            return await request_validation_exception_handler(request, error)
        issues = [{key: item[key] for key in ("loc", "msg", "type")} for item in error.errors()]
        return JSONResponse(
            status_code=422,
            content=error_body(422, "请求参数不符合要求", issues),
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, error: SQLAlchemyError):
        logger.error("Database error while handling %s", request.method, exc_info=error)
        if uses_envelope(request):
            return JSONResponse(status_code=500, content=error_body(500, "数据库暂时无法处理请求"))
        return JSONResponse(status_code=500, content={"detail": "数据库暂时无法处理请求"})
