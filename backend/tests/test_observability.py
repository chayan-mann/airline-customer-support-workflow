"""Every run produces structured events and exactly one turn_summary."""

import json

import pytest
from langchain_core.runnables import RunnableLambda

from app.agentic_ai.agents import booking
from app.agentic_ai.harness import RECURSION_LIMIT, run_config
from app.agentic_ai.harness.observability import LOG_FILE
from app.service import conversation_service
from tests.helpers import call, reply, send, summaries


def test_turn_is_fully_traced(route_to, script_agent, chat_id, user, harness_events):
    route_to("booking")
    script_agent(booking, call("search_faq", query="fees"), reply("No fees."))

    send(chat_id, user, "any fees?")

    kinds = [e["event"] for e in harness_events]
    assert kinds.count("turn_summary") == 1
    assert kinds.count("llm_end") == 2  # both booking_agent calls (classifier is faked outside the model)
    assert ("tool_start", "tool_end") == tuple(k for k in kinds if k.startswith("tool_"))

    summary = summaries(harness_events)[0]
    assert summary["outcome"] == "ok"
    assert summary["llm_calls"] == 2
    assert [t["tool"] for t in summary["tool_calls"]] == ["search_faq"]
    assert all(e["chat_id"] == chat_id and e["user_id"] == str(user.id) for e in harness_events)
    assert len({e["trace_id"] for e in harness_events}) == 1


def test_pending_approval_outcome(route_to, script_agent, chat_id, user, harness_events):
    route_to("booking")
    script_agent(booking, call("cancel_booking", confirmation_code="ABC123"))

    send(chat_id, user, "cancel")

    assert summaries(harness_events)[-1]["outcome"] == "pending_approval"


def test_failed_run_is_summarized_and_reraised(route_to, monkeypatch, chat_id, user, harness_events):
    def model_crash(_):
        raise RuntimeError("model exploded")

    route_to("booking")
    monkeypatch.setattr(booking, "_llm_with_tools", RunnableLambda(model_crash))

    with pytest.raises(RuntimeError):
        send(chat_id, user, "hi")

    summary = summaries(harness_events)[-1]
    assert summary["outcome"] == "error"
    assert "model exploded" in summary["error"]


def test_client_disconnect_is_summarized(route_to, script_agent, chat_id, user, harness_events):
    route_to("booking")
    script_agent(booking, reply("hi"))
    stream = conversation_service._stream_graph(
        {"messages": [("user", "hi")], "user_id": str(user.id)}, chat_id, user, "message"
    )

    next(stream)  # first status line, then the browser goes away
    stream.close()

    assert [s["outcome"] for s in summaries(harness_events)] == ["disconnected"]


def test_run_config_sets_limit_and_tracer():
    config, tracer = run_config("chat", "user", "message")
    assert config["recursion_limit"] == RECURSION_LIMIT
    assert config["callbacks"] == [tracer]
    assert config["configurable"]["thread_id"] == "chat"


def test_events_are_written_to_the_jsonl_file(route_to, script_agent, chat_id, user):
    route_to("booking")
    script_agent(booking, reply("hi"))

    send(chat_id, user, "hi")

    lines = [json.loads(line) for line in LOG_FILE.read_text().splitlines()]
    assert any(e["event"] == "turn_summary" and e["chat_id"] == chat_id for e in lines)
