from datetime import timedelta
from time import time
from typing import Annotated

import jwt
from fastapi import APIRouter, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from outfit_api.auth import read_token_claims

from outfit_api.dependencies import DbSession, require_browser_origin
from outfit_api.schemas import Credentials, ErrorResponse
from outfit_api.services.accounts import authenticate, register_account

router = APIRouter()
COOKIE_NAME = "outfit_token"
BROWSER_SESSION_LIFETIME = timedelta(days=1000)


@router.get("/browser-auth/login", tags=["浏览器登录"], response_class=HTMLResponse, summary="打开登录表单")
def browser_login_page():
    return """
    <!doctype html>
    <html lang="zh-CN">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>穿搭分析登录</title>
    </head>
    <body>
        <h1>穿搭分析登录</h1>
        <form method="post" action="/browser-auth/login">
            <p><label>用户名 <input name="username" autocomplete="username" required></label></p>
            <p><label>密码 <input name="password" type="password" autocomplete="current-password" required></label></p>
            <button type="submit">登录</button>
        </form>
    </body>
    </html>
    """


@router.post(
    "/browser-auth/login", tags=["浏览器登录"], response_class=RedirectResponse,
    status_code=303, summary="验证账号并设置 Cookie",
    responses={
        401: {"model": ErrorResponse, "description": "账号未注册或密码错误"},
        403: {"model": ErrorResponse, "description": "表单来源不符合要求"},
    },
)
def browser_login(request: Request, data: Annotated[Credentials, Form()], db: DbSession):
    require_browser_origin(request)
    return browser_session_response(db, data)


@router.post(
    "/browser-auth/register", tags=["浏览器登录"], response_class=RedirectResponse,
    status_code=303, summary="注册账号并保持登录",
    responses={409: {"model": ErrorResponse, "description": "用户名已被使用"}},
)
def browser_register(request: Request, data: Annotated[Credentials, Form()], db: DbSession):
    require_browser_origin(request)
    register_account(db, data)
    return browser_session_response(db, data)


def browser_session_response(db: DbSession, data: Credentials):
    result = authenticate(db, data, lifetime=BROWSER_SESSION_LIFETIME)
    response = RedirectResponse(url="/", status_code=303)
    set_login_cookie(response, result["access_token"], int(BROWSER_SESSION_LIFETIME.total_seconds()))
    return response


def set_login_cookie(response: Response, token: str, max_age: int):
    response.set_cookie(COOKIE_NAME, token, max_age=max_age, httponly=True, samesite="lax", path="/")


@router.post("/browser-auth/renew", tags=["浏览器登录"], status_code=204, response_class=Response)
def renew_browser_cookie(request: Request):
    require_browser_origin(request)
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return Response(status_code=401)
    try:
        remaining = read_token_claims(token)["exp"] - int(time())
    except jwt.InvalidTokenError:
        return Response(status_code=401)
    if remaining <= 0:
        return Response(status_code=401)
    response = Response(status_code=204)
    # 续存浏览器 Cookie，JWT 本身的到期时间保持不变。
    set_login_cookie(response, token, remaining)
    return response


@router.get("/browser-auth/logout", tags=["浏览器登录"], response_class=HTMLResponse, summary="打开退出确认页")
def browser_logout_page():
    return """
    <!doctype html>
    <html lang="zh-CN">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>退出穿搭分析</title>
    </head>
    <body>
        <h1>退出当前账号？</h1>
        <form method="post" action="/browser-auth/logout">
            <button type="submit">确认退出</button>
        </form>
        <p><a href="/">返回穿搭分析台</a></p>
    </body>
    </html>
    """


@router.post(
    "/browser-auth/logout", tags=["浏览器登录"], response_class=RedirectResponse,
    status_code=303, summary="清除 Cookie 并返回首页",
    responses={403: {"model": ErrorResponse, "description": "表单来源不符合要求"}},
)
def browser_logout(request: Request):
    require_browser_origin(request)
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, samesite="lax")
    return response
