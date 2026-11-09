from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from outfit_api.auth import token_user_id
from outfit_api.config import session
from outfit_api.crud.accounts import find_by_id

bearer = HTTPBearer(auto_error=False)


def get_db():
    with session() as db:
        yield db


DbSession = Annotated[Session, Depends(get_db)]


def current_user(
    auth: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    db: DbSession,
):
    if auth:
        try:
            user_id = token_user_id(auth.credentials)
            if find_by_id(db, user_id):
                return user_id
        except (jwt.InvalidTokenError, ValueError, TypeError):
            pass
    raise HTTPException(401, "请重新登录", headers={"WWW-Authenticate": "Bearer"})


Owner = Annotated[int, Depends(current_user)]


def require_browser_origin(request: Request):
    if request.headers.get("origin") != str(request.base_url).rstrip("/"):
        raise HTTPException(403, "请从本网站的页面提交")
