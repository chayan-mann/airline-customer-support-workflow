"""Read-only tool calls run straight away; anything with side effects pauses
for approval, and approve/reject resume the graph correctly."""

import types
from unittest.mock import Mock

import pytest
from langchain_core.messages import ToolMessage

from app.agentic_ai.agents import baggage, billing, booking
from app.agentic_ai.graph import TOOL_REJECTED_MESSAGE
from app.service import booking_service, conversation_service
from tests.helpers import approve, call, calls, reject, reply, send, state, summaries


@pytest.fixture
def fake_cancel(monkeypatch):
    flight = types.SimpleNamespace(
        flight_number="AI101", origin="DEL", destination="BOM", date="2026-10-01"
    )
    cancel = Mock(return_value=("ABC123", flight))
    monkeypatch.setattr(booking_service, "cancel_booking_by_confirmation_code", cancel)
    return cancel


def test_billing_lookups_run_without_approval(route_to, script_agent, chat_id, user, monkeypatch):
    from app.service import billing_service

    monkeypatch.setattr(billing_service, "list_payments_for_user", lambda db, user_id: [])
    route_to("billing")
    script_agent(billing, call("list_my_payments"), reply("You have no payments on file."))

    final = send(chat_id, user, "what have I paid?")

    assert final["status"] == "ok"
    assert state(chat_id).next == ()


def test_read_only_tool_runs_without_approval(route_to, script_agent, chat_id, user, harness_events):
    route_to("booking")
    script_agent(booking, call("search_faq", query="refund policy"), reply("Refunds take 5 days."))

    final = send(chat_id, user, "what's the refund policy?")

    assert final["status"] == "ok"
    assert final["reply"] == "Refunds take 5 days."
    assert state(chat_id).next == ()
    assert summaries(harness_events)[-1]["path"] == (
        "classify_intent → booking_agent → booking_read_tools → booking_agent"
    )


@pytest.mark.parametrize(
    "agent, tool, args, risk",
    [
        (booking, "select_seat", {"confirmation_code": "ABC123", "seat": "4C"}, "write"),
        (booking, "cancel_booking", {"confirmation_code": "ABC123"}, "destructive"),
        (baggage, "report_baggage_issue", {}, "write"),
        (billing, "request_refund", {"confirmation_code": "CAN111", "reason": "trip cancelled"}, "write"),
        (booking, "made_up_tool", {}, "destructive"),  # deny by default
    ],
)
def test_side_effect_tool_pauses_for_approval(route_to, script_agent, chat_id, user, agent, tool, args, risk):
    route_to(agent.NAME)
    script_agent(agent, call(tool, **args))

    final = send(chat_id, user, "do the thing")

    assert final["status"] == "pending_approval"
    assert [(p["name"], p["risk"]) for p in final["pending_tool_calls"]] == [(tool, risk)]
    assert state(chat_id).next == (f"{agent.NAME}_tools",)


def test_mixed_batch_pauses_for_approval(route_to, script_agent, chat_id, user):
    route_to("booking")
    script_agent(booking, calls(("search_faq", {"query": "fees"}), ("cancel_booking", {"confirmation_code": "ABC123"})))

    final = send(chat_id, user, "check fees and cancel")

    assert final["status"] == "pending_approval"
    assert {p["name"] for p in final["pending_tool_calls"]} == {"search_faq", "cancel_booking"}


def test_approve_runs_the_tool_and_continues(route_to, script_agent, chat_id, user, fake_cancel):
    route_to("booking")
    script_agent(
        booking,
        call("cancel_booking", confirmation_code="ABC123"),
        reply("Your booking ABC123 is cancelled."),
    )
    assert send(chat_id, user, "cancel ABC123")["status"] == "pending_approval"
    fake_cancel.assert_not_called()

    final = approve(chat_id, user)

    fake_cancel.assert_called_once()
    assert final["status"] == "ok"
    assert final["reply"] == "Your booking ABC123 is cancelled."
    assert state(chat_id).next == ()


def test_reject_skips_the_tool_and_tells_the_model(route_to, script_agent, chat_id, user, fake_cancel):
    route_to("booking")
    script_agent(
        booking,
        call("cancel_booking", confirmation_code="ABC123"),
        reply("Okay, I didn't cancel it."),
    )
    send(chat_id, user, "cancel ABC123")

    final = reject(chat_id, user)

    fake_cancel.assert_not_called()
    assert final["reply"] == "Okay, I didn't cancel it."
    tool_messages = [m for m in state(chat_id).values["messages"] if isinstance(m, ToolMessage)]
    assert [m.content for m in tool_messages] == [TOOL_REJECTED_MESSAGE]


def test_status_stream_ignores_interrupt_events():
    # Regression: the "__interrupt__" event carries a tuple, which used to
    # crash the status stream on every approval pause.
    assert conversation_service._describe_step("__interrupt__", ()) is None
