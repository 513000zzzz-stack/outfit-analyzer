import logging

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from outfit_api.auth import API_TOKEN_LIFETIME, check_password, hash_password, make_token
from outfit_api.crud.accounts import find_by_id, find_by_username
from outfit_api.models import User
from outfit_api.schemas import Credentials

audit = logging.getLogger("outfit_api.audit")


def issue_token(user: User, *, lifetime=API_TOKEN_LIFETIME):
    return make_token(user.id, lifetime=lifetime)


def register_account(db: Session, data: Credentials):
    username = data.username.lower()
    if find_by_username(db, username) is not None:
        audit.warning("注册失败 username=%s 原因=用户名已存在", username)
        raise HTTPException(409, "用户名已被使用")
    user = User(username=username, password_hash=hash_password(data.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError as error:
        # 并发注册同名账号时由唯一索引兜底。
        db.rollback()
        audit.warning("注册失败 username=%s 原因=并发冲突", username)
        raise HTTPException(409, "用户名已被使用") from error
    audit.info("注册成功 username=%s id=%s", user.username, user.id)
    return user


def verify_credentials(db: Session, data: Credentials):
    username = data.username.lower()
    user = find_by_username(db, username)
    if user is None:
        audit.warning("登录失败 username=%s 原因=账号未注册", username)
        raise HTTPException(401, "该账号尚未注册，请先注册。")
    if not check_password(data.password, user.password_hash):
        audit.warning("登录失败 username=%s 原因=密码错误", username)
        raise HTTPException(401, "密码错误，请重新输入。")
    audit.info("登录成功 username=%s id=%s", user.username, user.id)
    return user


def authenticate(db: Session, data: Credentials, *, lifetime=API_TOKEN_LIFETIME):
    user = verify_credentials(db, data)
    return {"access_token": issue_token(user, lifetime=lifetime), "token_type": "bearer"}


def read_account(db: Session, owner_id: int):
    user = find_by_id(db, owner_id)
    if user is None:
        raise HTTPException(401, "请重新登录")
    return user
