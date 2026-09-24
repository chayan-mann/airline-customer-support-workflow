"""Agent harness: cross-cutting infrastructure wrapped around graph runs
(currently observability; security and reliability layers go here too)."""

from app.agentic_ai.harness.observability import HarnessTracer


def run_config(chat_id: str, user_id: str, kind: str) -> tuple[dict, HarnessTracer]:
    """Config for one graph run, with the tracer attached. Use this for
    graph.stream(); plain state reads can keep using the bare thread config."""
    tracer = HarnessTracer(chat_id, user_id, kind)
    config = {
        "configurable": {"thread_id": chat_id},
        "callbacks": [tracer],
        "tags": [f"kind:{kind}"],
        "metadata": {"chat_id": chat_id, "user_id": user_id, "trace_id": tracer.trace_id},
    }
    return config, tracer
