from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from langchain_core.messages import ToolMessage
from pydantic import BaseModel

from app.graph import TOOL_REJECTED_MESSAGE, graph

load_dotenv()

app = FastAPI(title="AI Customer Support Agent")


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


def _config(session_id: str) -> dict:
    return {"configurable": {"thread_id": session_id}}


def _pending_tool_calls(config: dict) -> list[dict]:
    """Return tool calls the graph is currently paused on, if any."""
    state = graph.get_state(config)
    if "tools" not in state.next:
        return []
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


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    config = _config(request.session_id)

    # LangGraph automatically pulls the past history for this thread_id and appends your new message to it!
    # If the run hits a tool call, execution pauses before the "tools" node
    # and graph.invoke returns the paused state instead of a final reply.
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

    # Resuming with None re-enters at the interrupted "tools" node and runs it for real.
    graph.invoke(None, config=config)
    return _respond(config)


@app.post("/reject", response_model=ChatResponse)
def reject(request: SessionRequest):
    """Block the pending tool call from executing and tell the model it was denied."""
    config = _config(request.session_id)
    pending = _pending_tool_calls(config)
    if not pending:
        raise HTTPException(status_code=400, detail="No pending tool call for this session")

    # Fake the "tools" node's output with a rejection message instead of
    # actually running the tool, then resume from right after "tools".
    rejection_messages = [
        ToolMessage(content=TOOL_REJECTED_MESSAGE, tool_call_id=tc["id"])
        for tc in pending
    ]
    graph.update_state(config, {"messages": rejection_messages}, as_node="tools")
    graph.invoke(None, config=config)
    return _respond(config)
