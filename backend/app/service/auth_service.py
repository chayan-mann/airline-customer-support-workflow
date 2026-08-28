"""Business logic behind the /auth/* routes."""

import uuid

from fastapi import HTTPException, Response
from sqlalchemy.orm import Session

from app.models import User
from app.schema.auth import UserOut
from app.security import (
    COOKIE_NAME,
    create_access_token,
    hash_password,
    token_max_age_seconds,
    verify_password,
)


def _issue_auth_cookie(response: Response, user_id: uuid.UUID) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=create_access_token(user_id),
        httponly=True,
        samesite="lax",
        secure=False,  # set True once served over HTTPS
        max_age=token_max_age_seconds(),
    )


def _to_user_out(user: User) -> UserOut:
    return UserOut(id=str(user.id), email=user.email)


def register_user(db: Session, response: Response, email: str, password: str) -> UserOut:
    email = email.strip().lower()
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    if db.query(User).filter(User.email == email).first() is not None:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(email=email, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)

    _issue_auth_cookie(response, user.id)
    return _to_user_out(user)


def authenticate_user(db: Session, response: Response, email: str, password: str) -> UserOut:
    email = email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if user is None or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    _issue_auth_cookie(response, user.id)
    return _to_user_out(user)



def logout(response: Response) -> None:
    # Stateless: the token itself stays valid until it expires, but the
    # browser no longer holds/sends it once the cookie is cleared.
    response.delete_cookie(COOKIE_NAME)


def current_user_out(current_user: User) -> UserOut:
    return _to_user_out(current_user)
