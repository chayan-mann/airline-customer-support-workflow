from datetime import datetime

from pydantic import BaseModel


class CreateChatRequest(BaseModel):
    title: str | None = None


class RenameChatRequest(BaseModel):
    title: str


class ChatOut(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
