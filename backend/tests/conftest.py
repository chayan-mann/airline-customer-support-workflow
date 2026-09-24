"""Offline test setup: the real graph and harness, with Postgres, the FAQ
embeddings and Ollama replaced by in-memory fakes. Nothing here needs a
running database or model server.

The stubs below must be in place before any `app.*` module is imported,
since several of them connect to Postgres or Ollama at import time.
"""

import json
import logging
import os
import sys
import tempfile
import types
import uuid

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
# Keep test runs out of the real backend/logs/harness.jsonl.
os.environ["HARNESS_LOG_DIR"] = tempfile.mkdtemp(prefix="harness-test-logs-")

# FAQ knowledge base: embeds every FAQ with Ollama on import.
_kb = types.ModuleType("app.agentic_ai.knowledge_base")
_kb.search = lambda query: []
sys.modules["app.agentic_ai.knowledge_base"] = _kb

# Checkpointer: in-memory instead of Postgres.
import langgraph.checkpoint.postgres as _pg  # noqa: E402
import psycopg_pool  # noqa: E402
from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402


class _InMemoryPostgresSaver(InMemorySaver):
    def __init__(self, conn=None):
        super().__init__()

    def setup(self):
        pass


_pg.PostgresSaver = _InMemoryPostgresSaver
psycopg_pool.ConnectionPool = lambda *args, **kwargs: None

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel  # noqa: E402
from langchain_core.runnables import RunnableLambda  # noqa: E402

from app.agentic_ai import classifier  # noqa: E402
from app.agentic_ai.harness import reliability  # noqa: E402
from app.service import conversation_service  # noqa: E402


@pytest.fixture(autouse=True)
def no_retry_backoff(monkeypatch):
    """Keep retry behavior, drop the real-time waits between attempts."""
    monkeypatch.setattr(reliability, "LLM_BACKOFF", {"initial": 0, "max": 0, "jitter": 0})


@pytest.fixture
def harness_events():
    """Every JSON event the harness logs during the test, parsed, in order."""
    events: list[dict] = []

    class _Capture(logging.Handler):
        def emit(self, record):
            events.append(json.loads(record.getMessage()))

    handler = _Capture()
    logger = logging.getLogger("harness")
    logger.addHandler(handler)
    yield events
    logger.removeHandler(handler)


@pytest.fixture
def route_to(monkeypatch):
    """Make the intent classifier return a fixed intent (or raise)."""

    def _route(intent: str | None = None, error: Exception | None = None):
        def classify(messages, schema):
            if error is not None:
                raise error
            return schema(intent=intent)

        fake_llm = types.SimpleNamespace(
            with_structured_output=lambda schema: RunnableLambda(lambda m: classify(m, schema))
        )
        monkeypatch.setattr(classifier, "llm", fake_llm)

    return _route


@pytest.fixture
def script_agent(monkeypatch):
    """Replace a specialist's model with one that replies with the given
    messages, in order, one per LLM call."""

    def _script(agent_module, *messages):
        monkeypatch.setattr(
            agent_module, "_llm_with_tools", GenericFakeChatModel(messages=iter(messages))
        )

    return _script


@pytest.fixture
def user():
    return types.SimpleNamespace(id=uuid.uuid4())


@pytest.fixture
def chat_id():
    return str(uuid.uuid4())


@pytest.fixture(autouse=True)
def skip_chat_ownership_check(monkeypatch):
    """approve/reject look the chat up in Postgres first; there is none."""
    monkeypatch.setattr(conversation_service, "get_owned_chat", lambda chat_id, user, db: None)
