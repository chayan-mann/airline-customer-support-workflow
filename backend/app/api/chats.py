from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.schema.chats import ChatOut, CreateChatRequest
from app.security import get_current_user
from app.service import chats_service

router = APIRouter()


@router.get("/chats", response_model=list[ChatOut])
def list_chats(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    return chats_service.list_user_chats(db, current_user)


@router.post("/chats", response_model=ChatOut)
def create_chat(
    payload: CreateChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return chats_service.create_chat(db, current_user, payload.title)
