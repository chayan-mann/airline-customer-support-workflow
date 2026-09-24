"""LLM retries on transient errors only, and the classifier falls back to
the general agent when it can't classify."""

from types import SimpleNamespace

import httpx
import pytest
from langchain_core.exceptions import OutputParserException
from langchain_core.runnables import RunnableLambda

from app.agentic_ai import classifier
from app.agentic_ai.agents import general
from app.agentic_ai.classifier import classify_intent
from app.agentic_ai.harness.reliability import LLM_MAX_ATTEMPTS, with_llm_retry
from app.agentic_ai.llm import llm
from tests.helpers import reply, send, summaries


def flaky(error: Exception, fail_times: int):
    """A runnable that raises `error` the first `fail_times` calls."""
    attempts = []

    def run(_):
        attempts.append(1)
        if len(attempts) <= fail_times:
            raise error
        return "ok"

    return RunnableLambda(run), attempts


@pytest.mark.parametrize(
    "error", [httpx.ReadTimeout("slow"), httpx.ConnectError("refused"), ConnectionError("down")]
)
def test_transient_errors_are_retried(error):
    runnable, attempts = flaky(error, fail_times=LLM_MAX_ATTEMPTS - 1)
    assert with_llm_retry(runnable).invoke(None) == "ok"
    assert len(attempts) == LLM_MAX_ATTEMPTS


def test_gives_up_after_max_attempts():
    runnable, attempts = flaky(httpx.ReadTimeout("slow"), fail_times=99)
    with pytest.raises(httpx.ReadTimeout):
        with_llm_retry(runnable).invoke(None)
    assert len(attempts) == LLM_MAX_ATTEMPTS


def test_bugs_are_not_retried():
    runnable, attempts = flaky(ValueError("bug"), fail_times=99)
    with pytest.raises(ValueError):
        with_llm_retry(runnable).invoke(None)
    assert len(attempts) == 1


def test_ollama_requests_have_a_timeout():
    llm._set_clients()
    assert llm._client._client.timeout.read is not None


def test_classifier_retries_malformed_output(monkeypatch):
    runnable, attempts = flaky(OutputParserException("not json"), fail_times=1)
    ok = SimpleNamespace(intent="baggage")
    monkeypatch.setattr(
        classifier,
        "llm",
        SimpleNamespace(with_structured_output=lambda schema: runnable | RunnableLambda(lambda _: ok)),
    )

    assert classify_intent({"messages": [("user", "my bag is lost")]}) == {"intent": "baggage"}
    assert len(attempts) == 2


def test_classifier_falls_back_to_general(route_to, script_agent, chat_id, user, harness_events):
    route_to(error=OutputParserException("not json"))
    script_agent(general, reply("Happy to help!"))

    final = send(chat_id, user, "hmm")

    assert final["reply"] == "Happy to help!"
    assert summaries(harness_events)[-1]["path"] == "classify_intent → general_agent"
    assert any(e["event"] == "classifier_fallback" for e in harness_events)
