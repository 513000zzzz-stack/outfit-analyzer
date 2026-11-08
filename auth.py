import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt


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
    salt, expected = saved.split(":")
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), 600_000
    )
    return hmac.compare_digest(digest.hex(), expected)


def make_token(user_id):
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": str(user_id), "iat": now, "exp": now + timedelta(hours=2)},
        signing_key(),
        algorithm="HS256",
    )


def token_user_id(token):
    claims = jwt.decode(
        token, signing_key(), algorithms=["HS256"],
        options={"require": ["sub", "iat", "exp"]},
    )
    return int(claims["sub"])
