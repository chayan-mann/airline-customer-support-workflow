"""Reliability layer: keep one failing tool or LLM call from crashing the
whole chat turn."""

from langgraph.prebuilt.tool_node import ToolInvocationError

TOOL_INTERNAL_ERROR_MESSAGE = (
    "ERROR: this action failed due to an internal error. Do not retry it and "
    "do not guess a result — tell the user something went wrong on our side "
    "and ask them to try again in a moment."
)


def handle_tool_error(e: Exception) -> str:
    """ToolNode `handle_tool_errors` callback: turn a tool exception into a
    ToolMessage the model can read instead of an exception that aborts the run.

    The exception itself still reaches the harness tracer (tool_error event).
    """
    # The model sent bad arguments (wrong type, missing field): tell it
    # exactly what was wrong so it can correct the call.
    if isinstance(e, ToolInvocationError):
        return e.message
    # Anything else (DB down, bug in a tool): don't invite a retry, since
    # the failed call may be a write like create_booking.
    return TOOL_INTERNAL_ERROR_MESSAGE
