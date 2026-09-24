"""Measure whether each specialist agent picks the right tool, with the right
arguments, for a message — and never takes a forbidden shortcut.

Runs every case in tool_choice_cases.jsonl through the real agent (same
prompt, model, bound tools and retries) against your local Ollama, and grades
the model's *next step* only: which tool it calls, or whether it replies
without one. Tools are never executed, so this needs Ollama but not
Postgres.

    cd backend
    venv/bin/python -m evals.tool_choice_eval
    venv/bin/python -m evals.tool_choice_eval --repeat 3   # catch flaky cases
    venv/bin/python -m evals.tool_choice_eval --only move-step2-uses-picked-token

Case format (one JSON object per line):
    id        short name, shown in the report
    agent     booking | baggage | billing | general  (the classifier is
              bypassed — it has its own eval)
    history   optional earlier turns, so a case can start mid-flow:
              {"role": "user"|"assistant", "content": ...},
              {"role": "assistant", "tool_calls": [{"name", "args"}]},
              {"role": "tool", "name": ..., "content": ...}
    message   the user's latest message
    expect    acceptable first tool names; "none" = replies without a tool
    args      optional: argument values the first call must have
              (compared as trimmed, case-insensitive strings)
    forbid    optional: tools that must not be called at all in this step

Exits non-zero when the pass rate is below --min-pass-rate.
"""

import argparse
import json
import os
import sys
import time
import types
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

load_dotenv()
# app.db.session needs a URL at import; nothing here opens a connection.
os.environ.setdefault("DATABASE_URL", "postgresql://unused:unused@localhost:5432/unused")

# Tools are never executed, so skip embedding the whole FAQ with Ollama
# at import (the model still sees search_faq's name and description).
_kb = types.ModuleType("app.agentic_ai.knowledge_base")
_kb.search = lambda query: []
sys.modules["app.agentic_ai.knowledge_base"] = _kb

from app.agentic_ai.agents import SPECIALIST_AGENTS  # noqa: E402

CASES_FILE = Path(__file__).parent / "tool_choice_cases.jsonl"
AGENTS = {agent.NAME: agent for agent in SPECIALIST_AGENTS}


def build_messages(case: dict) -> list:
    """Turn a case's history + message into LangChain messages, linking each
    tool result to the most recent assistant call of that tool."""
    messages = []
    open_calls: dict[str, str] = {}
    for i, turn in enumerate(case.get("history", [])):
        if turn["role"] == "user":
            messages.append(HumanMessage(turn["content"]))
        elif turn["role"] == "assistant" and turn.get("tool_calls"):
            tool_calls = []
            for j, tc in enumerate(turn["tool_calls"]):
                call_id = f"call_{i}_{j}"
                open_calls[tc["name"]] = call_id
                tool_calls.append({"name": tc["name"], "args": tc["args"], "id": call_id})
            messages.append(AIMessage(content="", tool_calls=tool_calls))
        elif turn["role"] == "assistant":
            messages.append(AIMessage(turn["content"]))
        elif turn["role"] == "tool":
            messages.append(
                ToolMessage(turn["content"], name=turn["name"], tool_call_id=open_calls.pop(turn["name"]))
            )
    messages.append(HumanMessage(case["message"]))
    return messages


def _norm(value) -> str:
    return str(value).strip().lower()


def grade(case: dict, response: AIMessage) -> tuple[bool, str]:
    """Return (passed, what the model did / why it failed)."""
    calls = getattr(response, "tool_calls", None) or []
    names = [tc["name"] for tc in calls]
    did = ", ".join(f"{tc['name']}({json.dumps(tc['args'])})" for tc in calls) or "none (replied)"

    forbidden = sorted(set(names) & set(case.get("forbid", [])))
    if forbidden:
        return False, f"{did}  ← forbidden: {', '.join(forbidden)}"

    first = names[0] if names else "none"
    if first not in case["expect"]:
        return False, f"{did}  ← expected {' or '.join(case['expect'])}"

    if calls and case.get("args"):
        actual = calls[0]["args"]
        wrong = [
            f"{key}={actual.get(key)!r} (want {want!r})"
            for key, want in case["args"].items()
            if _norm(actual.get(key, "")) != _norm(want)
        ]
        if wrong:
            return False, f"{did}  ← wrong args: {'; '.join(wrong)}"

    return True, did


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--min-pass-rate", type=float, default=0.8)
    parser.add_argument("--repeat", type=int, default=1, help="runs per case, to spot flaky behavior")
    parser.add_argument("--only", help="run a single case by id")
    parser.add_argument("--cases", type=Path, default=CASES_FILE)
    args = parser.parse_args()

    cases = [json.loads(line) for line in args.cases.read_text().splitlines() if line.strip()]
    if args.only:
        cases = [c for c in cases if c["id"] == args.only]
        if not cases:
            print(f"no case with id {args.only!r}")
            return 2

    passed_runs = 0
    total_runs = 0
    failures: list[tuple[str, str, int, int]] = []
    started = time.perf_counter()

    for i, case in enumerate(cases, 1):
        agent = AGENTS[case["agent"]]
        messages = build_messages(case)
        results = []
        for _ in range(args.repeat):
            response = agent.node({"messages": messages})["messages"][0]
            results.append(grade(case, response))

        ok_count = sum(ok for ok, _ in results)
        passed_runs += ok_count
        total_runs += len(results)
        mark = "✓" if ok_count == len(results) else ("~" if ok_count else "✗")
        rate = f" {ok_count}/{len(results)}" if args.repeat > 1 else ""
        print(f"[{i:>2}/{len(cases)}] {mark}{rate} {case['agent']:<8} {case['id']:<42} {results[-1][1]}")
        if ok_count < len(results):
            first_failure = next(detail for ok, detail in results if not ok)
            failures.append((case["id"], first_failure, ok_count, len(results)))

    elapsed = time.perf_counter() - started
    pass_rate = passed_runs / total_runs

    if failures:
        print("\nFailures:")
        for case_id, detail, ok_count, runs in failures:
            flaky = f" (passed {ok_count}/{runs})" if ok_count else ""
            print(f"  {case_id}{flaky}: {detail}")
    print(
        f"\nPass rate: {pass_rate:.0%} ({passed_runs}/{total_runs} runs) · "
        f"{elapsed / total_runs:.1f}s per run"
    )

    if pass_rate < args.min_pass_rate:
        print(f"FAIL: below --min-pass-rate {args.min_pass_rate:.0%}")
        return 1
    print(f"PASS: at or above --min-pass-rate {args.min_pass_rate:.0%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
