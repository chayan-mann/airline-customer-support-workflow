"""A runaway agent loop is cut off at RECURSION_LIMIT and the chat recovers."""

from app.agentic_ai.agents import booking
from app.agentic_ai.harness import RECURSION_LIMIT
from app.service.conversation_service import STEP_LIMIT_REPLY
from tests.helpers import call, reply, send, state, summaries

# classify (1 step) + agent (1) + N × (read_tools + agent) = 2 + 2N steps,
# so this is the last tool round that fits inside the limit.
LAST_ROUND_IN_LIMIT = (RECURSION_LIMIT - 2) // 2


def faq_loop(n):
    return [call("search_faq", query=f"try {i}") for i in range(n)]


def test_runaway_loop_ends_with_apology(route_to, script_agent, chat_id, user, harness_events):
    route_to("booking")
    script_agent(booking, *faq_loop(100))

    final = send(chat_id, user, "help")

    assert final["status"] == "ok"
    assert final["reply"] == STEP_LIMIT_REPLY
    assert state(chat_id).next == ()
    assert summaries(harness_events)[-1]["outcome"] == "step_limit"


def test_chat_keeps_working_after_the_cutoff(route_to, script_agent, chat_id, user):
    route_to("booking")
    script_agent(booking, *faq_loop(100))
    send(chat_id, user, "help")

    script_agent(booking, reply("Hi again!"))
    assert send(chat_id, user, "hello?")["reply"] == "Hi again!"


def test_write_on_last_allowed_step_still_asks_for_approval(route_to, script_agent, chat_id, user):
    route_to("booking")
    script_agent(booking, *faq_loop(LAST_ROUND_IN_LIMIT), call("cancel_booking", confirmation_code="A"))

    final = send(chat_id, user, "cancel")

    assert final["status"] == "pending_approval"


def test_write_past_the_limit_is_dropped_not_left_pending(route_to, script_agent, chat_id, user):
    route_to("booking")
    script_agent(booking, *faq_loop(LAST_ROUND_IN_LIMIT + 1), call("cancel_booking", confirmation_code="A"))

    final = send(chat_id, user, "cancel")

    assert final["status"] == "ok"
    assert final["reply"] == STEP_LIMIT_REPLY
    assert final["pending_tool_calls"] is None
    assert state(chat_id).next == ()
