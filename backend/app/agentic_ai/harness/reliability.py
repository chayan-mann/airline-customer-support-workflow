"""Reliability layer: keep one failing tool or LLM call from crashing the
whole chat turn."""

import httpx
from langchain_core.runnables import Runnable
from langchain_core.runnables.retry import ExponentialJitterParams
from langgraph.prebuilt.tool_node import ToolInvocationError

TOOL_INTERNAL_ERROR_MESSAGE = (
    "ERROR: this action failed due to an internal error. Do not retry it and "
    "do not guess a result — tell the user something went wrong on our side "
    "and ask them to try again in a moment."
)


LLM_MAX_ATTEMPTS = 3
# Wait ~1s, ~2s, … (+ up to 1s jitter) between attempts, capped at 10s.
LLM_BACKOFF: ExponentialJitterParams = {"initial": 1, "max": 10, "jitter": 1}

# Transient failures talking to Ollama: timeouts, dropped connections
# (ollama raises the builtin ConnectionError when it can't connect at all).
TRANSIENT_LLM_ERRORS: tuple[type[Exception], ...] = (httpx.TransportError, ConnectionError)


def with_llm_retry(
    runnable: Runnable, extra_retry_on: tuple[type[Exception], ...] = ()
) -> Runnable:
    """Retry an LLM call on transient errors with jittered exponential
    backoff. Apply it to the final runnable (after bind_tools /
    with_structured_output), since the retry wrapper doesn't expose those.

    Safe for LLM calls only — they have no side effects. Never wrap tools.
    Each failed attempt still shows up as an llm_error event in the trace.
    """
    return runnable.with_retry(
        retry_if_exception_type=TRANSIENT_LLM_ERRORS + extra_retry_on,
        wait_exponential_jitter=True,
        exponential_jitter_params=LLM_BACKOFF,
        stop_after_attempt=LLM_MAX_ATTEMPTS,
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
