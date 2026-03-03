"""Authentication service – user creation and credential verification."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from garage_agent.core.security import get_password_hash, verify_password
from garage_agent.db.models import User


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    """Return the user if email exists and password matches, else None."""
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def create_user(
    db: Session,
    garage_id: int,
    email: str,
    password: str,
    role: str = "OWNER",
) -> User:
    """Hash password and persist a new User row."""
    user = User(
        garage_id=garage_id,
        email=email,
        hashed_password=get_password_hash(password),
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
