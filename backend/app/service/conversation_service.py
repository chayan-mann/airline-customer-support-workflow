"""Business logic behind /chat, /approve, /reject, and /history/{chat_id}.

Owns all direct interaction with the compiled LangGraph `graph` object.
"""

import uuid

from fastapi import HTTPException
from langchain_core.messages import ToolMessage
from sqlalchemy.orm import Session

from app.agentic_ai.graph import TOOL_NODE_NAMES, TOOL_REJECTED_MESSAGE, graph
from app.models import Chat, User
from app.schema.conversation import ChatResponse, HistoryMessage, HistoryResponse, PendingToolCall


def _thread_config(chat_id: str) -> dict:
    return {"configurable": {"thread_id": chat_id}}


def get_owned_chat(chat_id: str, user: User, db: Session) -> Chat:
    """Look up a chat and confirm it belongs to the given user."""
    try:
        chat_uuid = uuid.UUID(chat_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Chat not found")

    chat = db.get(Chat, chat_uuid)
    if chat is None or chat.user_id != user.id:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat


def _pending_tool_node(config: dict) -> str | None:
    """Return the tool node name the graph is currently paused on, if any."""
    state = graph.get_state(config)
    pending = set(state.next) & TOOL_NODE_NAMES
    return next(iter(pending), None)


def _pending_tool_calls(config: dict) -> list[dict]:
    """Return tool calls the graph is currently paused on, if any."""
    if _pending_tool_node(config) is None:
        return []
    state = graph.get_state(config)
    last_message = state.values["messages"][-1]
    return getattr(last_message, "tool_calls", None) or []


def _build_response(config: dict) -> ChatResponse:
    pending = _pending_tool_calls(config)
    if pending:
        return ChatResponse(
            status="pending_approval",
            pending_tool_calls=[
                PendingToolCall(id=tc["id"], name=tc["name"], args=tc["args"])
                for tc in pending
            ],
        )
    state = graph.get_state(config)
    return ChatResponse(status="ok", reply=state.values["messages"][-1].content)


def get_history(chat_id: str, user: User, db: Session) -> HistoryResponse:
    """Return a chat's prior conversation, so a fresh browser tab can
    resume an existing chat instead of showing an empty window."""
    get_owned_chat(chat_id, user, db)
    config = _thread_config(chat_id)
    state = graph.get_state(config)
    raw_messages = state.values.get("messages", [])

    messages = []
    for msg in raw_messages:
        if msg.type == "human":
            messages.append(HistoryMessage(role="user", content=msg.content))
        elif msg.type == "ai" and msg.content:
            messages.append(HistoryMessage(role="agent", content=msg.content))

    pending = _pending_tool_calls(config)
    pending_tool_calls = (
        [PendingToolCall(id=tc["id"], name=tc["name"], args=tc["args"]) for tc in pending]
        if pending
        else None
    )
    return HistoryResponse(messages=messages, pending_tool_calls=pending_tool_calls)


def send_message(chat_id: str, message: str, user: User, db: Session) -> ChatResponse:
    get_owned_chat(chat_id, user, db)
    config = _thread_config(chat_id)

    # LangGraph automatically pulls the past history for this thread_id and appends your new message to it!
    # If the run hits a tool call, execution pauses before the relevant
    # specialist's "*_tools" node and graph.invoke returns the paused state
    # instead of a final reply.
    graph.invoke({"messages": [{"role": "user", "content": message}]}, config=config)
    return _build_response(config)


def approve_pending_tool(chat_id: str, user: User, db: Session) -> ChatResponse:
    """Let the pending tool call actually execute, then continue the graph."""
    get_owned_chat(chat_id, user, db)
    config = _thread_config(chat_id)
    if not _pending_tool_calls(config):
        raise HTTPException(status_code=400, detail="No pending tool call for this chat")

    # Resuming with None re-enters at the interrupted "*_tools" node and runs it for real.
    graph.invoke(None, config=config)
    return _build_response(config)


def reject_pending_tool(chat_id: str, user: User, db: Session) -> ChatResponse:
    """Block the pending tool call from executing and tell the model it was denied."""
    get_owned_chat(chat_id, user, db)
    config = _thread_config(chat_id)
    pending = _pending_tool_calls(config)
    if not pending:
        raise HTTPException(status_code=400, detail="No pending tool call for this chat")

    # Fake the pending tool node's output with a rejection message instead of
    # actually running the tool, then resume from right after that node.
    rejection_messages = [
        ToolMessage(content=TOOL_REJECTED_MESSAGE, tool_call_id=tc["id"])
        for tc in pending
    ]
    graph.update_state(
        config, {"messages": rejection_messages}, as_node=_pending_tool_node(config)
    )
    graph.invoke(None, config=config)
    return _build_response(config)
