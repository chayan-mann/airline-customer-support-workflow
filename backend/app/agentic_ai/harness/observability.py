"""Observability layer: one callback handler per graph run that emits a
structured JSON log line for every node, LLM call and tool call, plus a
single turn summary (latency, token usage, tool success) at the end.

LangGraph forwards the run's callbacks to every nested llm.invoke / tool
call, so agents and tools don't need to know this exists.
"""

import json
import logging
import os
import sys
import time
import uuid
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler

# HARNESS_LOG_DIR overrides the location (the test suite points it at a
# temp dir so test runs never write to the real log).
LOG_DIR = Path(
    os.getenv("HARNESS_LOG_DIR") or Path(__file__).resolve().parent.parent.parent.parent / "logs"
)
LOG_FILE = LOG_DIR / "harness.jsonl"

logger = logging.getLogger("harness")
if not logger.handlers:
    # uvicorn only configures its own loggers, so give ours plain
    # one-JSON-object-per-line handlers: stdout for live viewing, and a
    # rotating JSONL file (10 MB x 5 backups) for later querying.
    _formatter = logging.Formatter("%(message)s")

    _stdout_handler = logging.StreamHandler(sys.stdout)
    _stdout_handler.setFormatter(_formatter)
    logger.addHandler(_stdout_handler)

    LOG_DIR.mkdir(exist_ok=True)
    _file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    _file_handler.setFormatter(_formatter)
    logger.addHandler(_file_handler)

    logger.setLevel(logging.INFO)
    logger.propagate = False

_MAX_FIELD_CHARS = 200


def _truncate(value: Any) -> str:
    text = str(value)
    return text if len(text) <= _MAX_FIELD_CHARS else text[: _MAX_FIELD_CHARS - 3] + "..."


class HarnessTracer(BaseCallbackHandler):
    """Collects events and metrics for a single graph run (one chat turn,
    approval, or rejection)."""

    def __init__(self, chat_id: str, user_id: str, kind: str):
        self.trace_id = uuid.uuid4().hex[:12]
        self.ctx = {"trace_id": self.trace_id, "chat_id": chat_id, "user_id": user_id, "kind": kind}
        self._started_at = time.perf_counter()
        self._run_starts: dict[uuid.UUID, tuple[float, str]] = {}

        self.node_path: list[str] = []
        self.llm_calls = 0
        self.llm_ms = 0.0
        self.input_tokens = 0
        self.output_tokens = 0
        self.tool_calls: list[dict] = []
        self.errors: list[str] = []

    def _emit(self, event: str, **fields) -> None:
        logger.info(json.dumps({"event": event, **self.ctx, **fields}, default=str, ensure_ascii=False))

    def _elapsed_ms(self, run_id: uuid.UUID) -> tuple[float, str]:
        start, name = self._run_starts.pop(run_id, (time.perf_counter(), "unknown"))
        return (time.perf_counter() - start) * 1000, name

    # --- graph nodes -------------------------------------------------------

    def on_chain_start(self, serialized, inputs, *, run_id, parent_run_id=None, tags=None, metadata=None, **kwargs):
        # Only LangGraph node runs, not every inner runnable of a node.
        node = (metadata or {}).get("langgraph_node")
        if node and kwargs.get("name") == node:
            self.node_path.append(node)
            self._emit("node_start", node=node, step=(metadata or {}).get("langgraph_step"))

    # --- LLM calls ---------------------------------------------------------

    def on_chat_model_start(self, serialized, messages, *, run_id, parent_run_id=None, tags=None, metadata=None, **kwargs):
        node = (metadata or {}).get("langgraph_node", "outside_graph")
        self._run_starts[run_id] = (time.perf_counter(), node)

    def on_llm_end(self, response, *, run_id, parent_run_id=None, tags=None, **kwargs):
        ms, node = self._elapsed_ms(run_id)
        usage: dict = {}
        tool_calls: list[str] = []
        generations = response.generations[0] if response.generations else []
        message = getattr(generations[0], "message", None) if generations else None
        if message is not None:
            usage = getattr(message, "usage_metadata", None) or {}
            tool_calls = [tc["name"] for tc in getattr(message, "tool_calls", None) or []]

        self.llm_calls += 1
        self.llm_ms += ms
        self.input_tokens += usage.get("input_tokens", 0)
        self.output_tokens += usage.get("output_tokens", 0)
        self._emit(
            "llm_end",
            node=node,
            ms=round(ms),
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            requested_tools=tool_calls or None,
        )

    def on_llm_error(self, error, *, run_id, parent_run_id=None, tags=None, **kwargs):
        ms, node = self._elapsed_ms(run_id)
        self.errors.append(f"llm:{type(error).__name__}")
        self._emit("llm_error", node=node, ms=round(ms), error=_truncate(repr(error)))

    # --- tool calls --------------------------------------------------------

    def on_tool_start(self, serialized, input_str, *, run_id, parent_run_id=None, tags=None, metadata=None, inputs=None, **kwargs):
        name = kwargs.get("name") or (serialized or {}).get("name", "unknown")
        self._run_starts[run_id] = (time.perf_counter(), name)
        self._emit("tool_start", tool=name, args=_truncate(inputs if inputs is not None else input_str))

    def on_tool_end(self, output, *, run_id, parent_run_id=None, **kwargs):
        ms, name = self._elapsed_ms(run_id)
        result = getattr(output, "content", output)
        self.tool_calls.append({"tool": name, "ms": round(ms), "ok": True})
        self._emit("tool_end", tool=name, ms=round(ms), ok=True, result=_truncate(result))

    def on_tool_error(self, error, *, run_id, parent_run_id=None, **kwargs):
        ms, name = self._elapsed_ms(run_id)
        self.tool_calls.append({"tool": name, "ms": round(ms), "ok": False})
        self.errors.append(f"tool:{name}:{type(error).__name__}")
        self._emit("tool_error", tool=name, ms=round(ms), ok=False, error=_truncate(repr(error)))

    # --- turn summary ------------------------------------------------------

    def finish(self, outcome: str, error: BaseException | None = None) -> None:
        """Emit the one-line summary for this run. `outcome` is e.g. "ok",
        "pending_approval", "error" or "disconnected"."""
        if error is not None:
            self.errors.append(f"run:{type(error).__name__}")
        self._emit(
            "turn_summary",
            outcome=outcome,
            total_ms=round((time.perf_counter() - self._started_at) * 1000),
            path=" → ".join(self.node_path),
            llm_calls=self.llm_calls,
            llm_ms=round(self.llm_ms),
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            tool_calls=self.tool_calls,
            errors=self.errors or None,
            error=_truncate(repr(error)) if error is not None else None,
        )
