from sqlalchemy import select
from sqlalchemy.orm import Session

from outfit_api.models import User


def find_by_username(db: Session, username: str):
    return db.scalar(select(User).where(User.username == username))


def find_by_id(db: Session, user_id: int):
    return db.get(User, user_id)
