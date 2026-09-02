"""Business logic behind /chat, /approve, /reject, and /history/{chat_id}.

Owns all direct interaction with the compiled LangGraph `graph` object.
"""

import json
import uuid
from typing import Iterator

from fastapi import HTTPException
from langchain_core.messages import ToolMessage
from sqlalchemy.orm import Session

from app.agentic_ai.graph import TOOL_NODE_NAMES, TOOL_REJECTED_MESSAGE, graph
from app.agentic_ai.llm import llm
from app.models import Chat, User
from app.schema.conversation import ChatResponse, HistoryMessage, HistoryResponse, PendingToolCall

TITLE_SYSTEM_PROMPT = (
    "Summarize the user's message into a short chat title: 3-6 words, title "
    "case, no quotation marks, no trailing punctuation. Reply with only the "
    "title, nothing else."
)

# Friendly status text for each graph node, shown to the user while a
# request is in flight instead of a single static spinner (see _stream_graph).
AGENT_STATUS_MESSAGES = {
    "classify_intent": "Understanding your request…",
    "booking_agent": "Looking into your booking…",
    "baggage_agent": "Looking into your baggage question…",
    "billing_agent": "Looking into your billing question…",
    "general_agent": "Looking into that…",
    "escalation_agent": "Connecting you to a specialist…",
}


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


def _describe_step(node_name: str, node_output: dict) -> str | None:
    """Turn one LangGraph node's output into a short human status line, so
    the frontend can show live progress instead of one static spinner."""
    messages = node_output.get("messages") or []
    last = messages[-1] if messages else None
    tool_calls = getattr(last, "tool_calls", None) if last else None

    if tool_calls:
        names = ", ".join(tc["name"] for tc in tool_calls)
        return f"Calling {names}…"
    if node_name in AGENT_STATUS_MESSAGES:
        return AGENT_STATUS_MESSAGES[node_name]
    if node_name.endswith("_tools"):
        return "Got a result, thinking…"
    return None


def _stream_graph(
    graph_input, config: dict, extra_final_fields: dict | None = None
) -> Iterator[str]:
    """Run the graph, yielding one NDJSON line per step as a live status
    update, then a final line shaped like ChatResponse (the same payload
    send_message/approve/reject used to return directly, plus any
    extra_final_fields merged in — e.g. chat_title).
    """
    for event in graph.stream(graph_input, config=config, stream_mode="updates"):
        for node_name, node_output in event.items():
            text = _describe_step(node_name, node_output)
            if text:
                yield json.dumps({"type": "status", "text": text}) + "\n"

    response = _build_response(config)
    payload = {"type": "final", **response.model_dump()}
    if extra_final_fields:
        payload.update(extra_final_fields)
    yield json.dumps(payload) + "\n"


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


def _generate_chat_title(message: str) -> str:
    """Best-effort short title for a new chat, derived from its first message."""
    result = llm.invoke(
        [
            {"role": "system", "content": TITLE_SYSTEM_PROMPT},
            {"role": "user", "content": message},
        ]
    )
    title = (result.content or "").strip().strip('"').strip("'")
    return title[:100] if title else "New Chat"


def send_message(chat_id: str, message: str, user: User, db: Session) -> Iterator[str]:
    """Stream NDJSON status lines while the graph runs, ending with a final
    line shaped like ChatResponse — see _stream_graph."""
    chat = get_owned_chat(chat_id, user, db)
    config = _thread_config(chat_id)
    is_first_message = not graph.get_state(config).values.get("messages")

    new_title = None
    # Only auto-title chats still on the default name — respects a manual
    # rename the user made before sending anything.
    if is_first_message and chat.title == "New Chat":
        try:
            new_title = _generate_chat_title(message)
            chat.title = new_title
            db.commit()
        except Exception:
            # A title-generation hiccup (e.g. Ollama momentarily unreachable)
            # must never block sending the actual message.
            db.rollback()
            new_title = None

    # LangGraph automatically pulls the past history for this thread_id and appends your new message to it!
    # If the run hits a tool call, execution pauses before the relevant
    # specialist's "*_tools" node and graph.stream() stops yielding instead
    # of ever reaching a final reply.
    return _stream_graph(
        {
        "messages": [{"role": "user", "content": message}],
        "user_id": str(user.id)
        },
        config,
        extra_final_fields={"chat_title": new_title},
    )


def approve_pending_tool(chat_id: str, user: User, db: Session) -> Iterator[str]:
    """Let the pending tool call actually execute, then continue the graph
    (streamed the same way as send_message)."""
    get_owned_chat(chat_id, user, db)
    config = _thread_config(chat_id)
    if not _pending_tool_calls(config):
        raise HTTPException(status_code=400, detail="No pending tool call for this chat")

    # Resuming with None re-enters at the interrupted "*_tools" node and runs it for real.
    return _stream_graph(None, config)


def reject_pending_tool(chat_id: str, user: User, db: Session) -> Iterator[str]:
    """Block the pending tool call from executing and tell the model it was
    denied (streamed the same way as send_message)."""
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
    return _stream_graph(None, config)
