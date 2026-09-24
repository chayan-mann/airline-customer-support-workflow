import json
from itertools import count

from langchain_core.messages import AIMessage

from app.agentic_ai.graph import graph
from app.service import conversation_service

_ids = count()


def call(name: str, **args) -> AIMessage:
    """A model reply that requests one tool call."""
    return calls((name, args))


def calls(*requests: tuple[str, dict]) -> AIMessage:
    """A model reply that requests several tool calls in one step."""
    return AIMessage(
        content="",
        tool_calls=[{"name": n, "args": a, "id": f"call_{next(_ids)}"} for n, a in requests],
    )


def reply(text: str) -> AIMessage:
    return AIMessage(content=text)


def _collect(lines) -> dict:
    """Drain an NDJSON stream from conversation_service; return the final line."""
    parsed = [json.loads(line) for line in lines]
    assert parsed[-1]["type"] == "final"
    return parsed[-1]


def send(chat_id: str, user, text: str) -> dict:
    """Run one chat turn the way POST /chat does (minus auth and titling)."""
    graph_input = {"messages": [{"role": "user", "content": text}], "user_id": str(user.id)}
    return _collect(conversation_service._stream_graph(graph_input, chat_id, user, "message"))


def approve(chat_id: str, user) -> dict:
    return _collect(conversation_service.approve_pending_tool(chat_id, user, db=None))


def reject(chat_id: str, user) -> dict:
    return _collect(conversation_service.reject_pending_tool(chat_id, user, db=None))


def state(chat_id: str):
    return graph.get_state({"configurable": {"thread_id": chat_id}})


def summaries(events: list[dict]) -> list[dict]:
    return [e for e in events if e["event"] == "turn_summary"]
