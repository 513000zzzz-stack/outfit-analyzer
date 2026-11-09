"""请求日志：每个请求一行，包含耗时、用户和来源 IP。"""

import logging
from time import perf_counter

import jwt
from starlette.middleware.base import BaseHTTPMiddleware

from outfit_api.auth import read_token_claims

logger = logging.getLogger("outfit_api.request")

# 探针和接口文档每隔几秒就会访问一次，记进日志只会淹没业务记录。
SKIP_PATHS = {"/api/health", "/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}


def client_ip(request):
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "-"


def current_user_id(request):
    token = request.cookies.get("outfit_token", "")
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip() or token
    if not token:
        return "-"
    try:
        return read_token_claims(token)["sub"]
    except (jwt.InvalidTokenError, KeyError, ValueError):
        return "-"


class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path in SKIP_PATHS:
            return await call_next(request)
        started = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "%s %s 未处理异常 ip=%s", request.method, request.url.path, client_ip(request)
            )
            raise
        logger.info(
            "%s %s %s %.1fms user=%s ip=%s",
            request.method,
            request.url.path,
            response.status_code,
            (perf_counter() - started) * 1000,
            current_user_id(request),
            client_ip(request),
        )
        return response
