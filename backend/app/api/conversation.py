from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.schema.conversation import (
    ChatIdRequest,
    ChatResponse,
    HistoryResponse,
    SendMessageRequest,
)
from app.security import get_current_user
from app.service import conversation_service

router = APIRouter()


@router.get("/history/{chat_id}", response_model=HistoryResponse)
def history(
    chat_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return conversation_service.get_history(chat_id, current_user, db)


@router.post("/chat", response_model=ChatResponse)
def chat(
    request: SendMessageRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return conversation_service.send_message(request.chat_id, request.message, current_user, db)


@router.post("/approve", response_model=ChatResponse)
def approve(
    request: ChatIdRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return conversation_service.approve_pending_tool(request.chat_id, current_user, db)


@router.post("/reject", response_model=ChatResponse)
def reject(
    request: ChatIdRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return conversation_service.reject_pending_tool(request.chat_id, current_user, db)
