"""Agent harness: cross-cutting infrastructure wrapped around graph runs —
observability (tracer), security (tool risk policy) and reliability (tool
error handling, step limit)."""

from app.agentic_ai.harness.observability import HarnessTracer

# Max graph steps per run. A turn is classify → agent → (tools → agent)*,
# so 25 allows ~11 tool rounds before the run is cut off as a runaway loop.
RECURSION_LIMIT = 25


def run_config(chat_id: str, user_id: str, kind: str) -> tuple[dict, HarnessTracer]:
    """Config for one graph run, with the tracer attached. Use this for
    graph.stream(); plain state reads can keep using the bare thread config."""
    tracer = HarnessTracer(chat_id, user_id, kind)
    config = {
        "configurable": {"thread_id": chat_id},
        "recursion_limit": RECURSION_LIMIT,
        "callbacks": [tracer],
        "tags": [f"kind:{kind}"],
        "metadata": {"chat_id": chat_id, "user_id": user_id, "trace_id": tracer.trace_id},
    }
    return config, tracer
