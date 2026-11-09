from fastapi import APIRouter

from outfit_api.common.responses import UNAUTHORIZED, ok
from outfit_api.dependencies import DbSession, Owner
from outfit_api.schemas import ApiResponse, AuthData, Credentials, ErrorResponse, UserInfo
from outfit_api.services.accounts import (
    issue_token, read_account, register_account, verify_credentials,
)

router = APIRouter(prefix="/api/user", tags=["用户"])


def user_info(user) -> UserInfo:
    return UserInfo(id=user.id, username=user.username, bio=user.bio, avatar=user.avatar)


@router.post(
    "/register",
    summary="注册账号并签发访问令牌",
    response_model=ApiResponse[AuthData],
    responses={409: {"model": ErrorResponse, "description": "用户名已被使用"}},
)
def register(data: Credentials, db: DbSession):
    user = register_account(db, data)
    return ok(
        {"token": issue_token(user), "userInfo": user_info(user)},
        "注册成功",
    )


@router.post(
    "/login",
    summary="登录并签发访问令牌",
    response_model=ApiResponse[AuthData],
    responses=UNAUTHORIZED,
)
def login(data: Credentials, db: DbSession):
    user = verify_credentials(db, data)
    return ok(
        {"token": issue_token(user), "userInfo": user_info(user)},
        "登录成功",
    )


@router.get(
    "/info",
    summary="读取当前登录账号信息",
    response_model=ApiResponse[UserInfo],
    responses=UNAUTHORIZED,
)
def me(owner_id: Owner, db: DbSession):
    return ok(user_info(read_account(db, owner_id)))
