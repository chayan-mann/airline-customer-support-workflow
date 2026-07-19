from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.schema.auth import LoginRequest, RegisterRequest, UserOut
from app.security import get_current_user
from app.service import auth_service

router = APIRouter()


@router.post("/auth/register", response_model=UserOut)
def register(payload: RegisterRequest, response: Response, db: Session = Depends(get_db)):
    return auth_service.register_user(db, response, payload.email, payload.password)


@router.post("/auth/login", response_model=UserOut)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    return auth_service.authenticate_user(db, response, payload.email, payload.password)


@router.post("/auth/logout")
def logout(response: Response):
    auth_service.logout(response)
    return {"status": "ok"}


@router.get("/auth/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return auth_service.current_user_out(current_user)
