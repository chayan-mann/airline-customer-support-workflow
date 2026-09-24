"""A failing tool becomes a message the model can read, not a crashed turn."""

from langchain_core.messages import ToolMessage
from pydantic import BaseModel, ValidationError

from app.agentic_ai.agents import booking
from app.agentic_ai.harness.reliability import TOOL_INTERNAL_ERROR_MESSAGE, handle_tool_error
from app.service import booking_service
from langgraph.prebuilt.tool_node import ToolInvocationError
from tests.helpers import call, reply, send, state, summaries


def _validation_error() -> ValidationError:
    class Args(BaseModel):
        seat: str

    try:
        Args()
    except ValidationError as e:
        return e


def test_bad_arguments_tell_the_model_what_to_fix():
    error = ToolInvocationError("select_seat", _validation_error(), {"seatt": "4C"})
    message = handle_tool_error(error)
    assert "select_seat" in message
    assert "seat" in message


def test_internal_errors_tell_the_model_not_to_retry():
    assert handle_tool_error(ConnectionError("db down")) == TOOL_INTERNAL_ERROR_MESSAGE


def test_crashing_tool_does_not_break_the_turn(route_to, script_agent, chat_id, user, monkeypatch, harness_events):
    def db_down(*args, **kwargs):
        raise ConnectionError("server closed the connection")

    monkeypatch.setattr(booking_service, "list_bookings_for_user", db_down)
    route_to("booking")
    script_agent(booking, call("list_my_bookings"), reply("Sorry, something went wrong on our side."))

    final = send(chat_id, user, "show my bookings")

    assert final["status"] == "ok"
    tool_message = next(m for m in state(chat_id).values["messages"] if isinstance(m, ToolMessage))
    assert tool_message.status == "error"
    assert tool_message.content == TOOL_INTERNAL_ERROR_MESSAGE
    tool_calls = summaries(harness_events)[-1]["tool_calls"]
    assert [(t["tool"], t["ok"]) for t in tool_calls] == [("list_my_bookings", False)]
