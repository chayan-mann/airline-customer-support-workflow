from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.messages import ToolMessage
from pydantic import BaseModel

from app.graph import TOOL_NODE_NAMES, TOOL_REJECTED_MESSAGE, graph

load_dotenv()

app = FastAPI(title="AI Customer Support Agent")

# Allow the local Vite dev server to call this API cross-origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    session_id: str # added to track separate conversations
    message: str


class SessionRequest(BaseModel):
    session_id: str


class PendingToolCall(BaseModel):
    id: str
    name: str
    args: dict


class ChatResponse(BaseModel):
    status: str  # "ok" or "pending_approval"
    reply: str | None = None
    pending_tool_calls: list[PendingToolCall] | None = None


class HistoryMessage(BaseModel):
    role: str  # "user" or "agent"
    content: str


class HistoryResponse(BaseModel):
    messages: list[HistoryMessage]
    pending_tool_calls: list[PendingToolCall] | None = None


def _config(session_id: str) -> dict:
    return {"configurable": {"thread_id": session_id}}


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


def _respond(config: dict) -> ChatResponse:
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


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/history/{session_id}", response_model=HistoryResponse)
def history(session_id: str):
    """Return a session's prior conversation, so a fresh browser tab can
    resume an existing thread_id instead of showing an empty chat."""
    config = _config(session_id)
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


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    config = _config(request.session_id)

    # LangGraph automatically pulls the past history for this thread_id and appends your new message to it!
    # If the run hits a tool call, execution pauses before the relevant
    # specialist's "*_tools" node and graph.invoke returns the paused state
    # instead of a final reply.
    graph.invoke(
        {"messages": [{"role": "user", "content": request.message}]},
        config=config,
    )
    return _respond(config)


@app.post("/approve", response_model=ChatResponse)
def approve(request: SessionRequest):
    """Let the pending tool call actually execute, then continue the graph."""
    config = _config(request.session_id)
    if not _pending_tool_calls(config):
        raise HTTPException(status_code=400, detail="No pending tool call for this session")

    # Resuming with None re-enters at the interrupted "*_tools" node and runs it for real.
    graph.invoke(None, config=config)
    return _respond(config)


@app.post("/reject", response_model=ChatResponse)
def reject(request: SessionRequest):
    """Block the pending tool call from executing and tell the model it was denied."""
    config = _config(request.session_id)
    pending = _pending_tool_calls(config)
    if not pending:
        raise HTTPException(status_code=400, detail="No pending tool call for this session")

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
    return _respond(config)
