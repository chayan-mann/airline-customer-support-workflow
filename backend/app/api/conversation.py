from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.schema.conversation import ChatIdRequest, HistoryResponse, SendMessageRequest
from app.security import get_current_user
from app.service import conversation_service

router = APIRouter()

# NDJSON: one JSON object per line — {"type": "status", "text": ...} for each
# live progress update, then a final {"type": "final", ...ChatResponse} line.
# Lets the frontend show step-by-step progress instead of one blocking spinner.
NDJSON_MEDIA_TYPE = "application/x-ndjson"


@router.get("/history/{chat_id}", response_model=HistoryResponse)
def history(
    chat_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return conversation_service.get_history(chat_id, current_user, db)


@router.post("/chat")
def chat(
    request: SendMessageRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stream = conversation_service.send_message(request.chat_id, request.message, current_user, db)
    return StreamingResponse(stream, media_type=NDJSON_MEDIA_TYPE)


@router.post("/approve")
def approve(
    request: ChatIdRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stream = conversation_service.approve_pending_tool(request.chat_id, current_user, db)
    return StreamingResponse(stream, media_type=NDJSON_MEDIA_TYPE)


@router.post("/reject")
def reject(
    request: ChatIdRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stream = conversation_service.reject_pending_tool(request.chat_id, current_user, db)
    return StreamingResponse(stream, media_type=NDJSON_MEDIA_TYPE)
