from typing import Optional
from sqlalchemy.orm import Session

from app.api.users.users_model import User


def get_user_by_id(user_id: int, db: Session) -> Optional[User]:
    return db.query(User).filter(User.id == user_id).first()


def get_user_by_discord_id(discord_id: str, db: Session) -> Optional[User]:
    return db.query(User).filter(User.discord_id == discord_id).first()


def get_all_users(db: Session) -> list[User]:
    return db.query(User).order_by(User.created_at.desc()).all()


def get_users_by_status(status: str, db: Session) -> list[User]:
    return db.query(User).filter(User.status == status).order_by(User.created_at.desc()).all()


def update_user_status(user_id: int, status: str, db: Session) -> Optional[User]:
    user = get_user_by_id(user_id, db)
    if not user:
        return None
    user.status = status
    db.commit()
    db.refresh(user)
    return user


def delete_user(user_id: int, db: Session) -> bool:
    user = get_user_by_id(user_id, db)
    if not user:
        return False
    db.delete(user)
    db.commit()
    return True
