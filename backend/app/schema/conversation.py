from pydantic import BaseModel


class SendMessageRequest(BaseModel):
    chat_id: str
    message: str


class ChatIdRequest(BaseModel):
    chat_id: str


class PendingToolCall(BaseModel):
    id: str
    name: str
    args: dict


class ChatResponse(BaseModel):
    status: str  # "ok" or "pending_approval"
    reply: str | None = None
    pending_tool_calls: list[PendingToolCall] | None = None
    # Set only when this message was the chat's first and auto-titling
    # succeeded, so the frontend can update the sidebar without refetching.
    chat_title: str | None = None


class HistoryMessage(BaseModel):
    role: str  # "user" or "agent"
    content: str


class HistoryResponse(BaseModel):
    messages: list[HistoryMessage]
    pending_tool_calls: list[PendingToolCall] | None = None
