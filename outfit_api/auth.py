import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt


API_TOKEN_LIFETIME = timedelta(hours=2)


def signing_key():
    key = os.environ.get("JWT_SECRET", "")
    if len(key.encode()) < 32:
        raise RuntimeError("JWT_SECRET 至少需要 32 字节")
    return key


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600_000)
    return f"{salt.hex()}:{digest.hex()}"


def check_password(password, saved):
    try:
        salt, expected = saved.split(":", 1)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt), 600_000
        )
    except (ValueError, AttributeError):
        # 摘要格式损坏时按校验失败处理，不要抛出 500。
        return False
    return hmac.compare_digest(digest.hex(), expected)


def make_token(user_id, *, lifetime=API_TOKEN_LIFETIME):
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": str(user_id), "iat": now, "exp": now + lifetime},
        signing_key(),
        algorithm="HS256",
    )


def read_token_claims(token):
    return jwt.decode(
        token, signing_key(), algorithms=["HS256"],
        options={"require": ["sub", "iat", "exp"]},
    )


def token_user_id(token):
    return int(read_token_claims(token)["sub"])
