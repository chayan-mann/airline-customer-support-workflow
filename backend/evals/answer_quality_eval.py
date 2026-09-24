"""Measure whether the agents' FAQ answers are correct and grounded, scored
by an LLM judge against reference answers.

Each case asks a specialist agent a policy question and runs the real agent
loop (prompt, model, retries, and the real search_faq over the FAQ
embeddings) until it replies. Other tools aren't executed — these are
FAQ-only questions. A judge model then compares the reply to the reference
answer and to the FAQ text the agent actually retrieved:

  correctness  correct | partial | incorrect   (vs. the reference answer)
  grounded     true if every policy fact in the reply appears in the
               retrieved FAQ text — catches answers invented from the
               model's general knowledge, which the prompts forbid

Needs Ollama (chat + embedding models), not Postgres.

    cd backend
    venv/bin/python -m evals.answer_quality_eval
    venv/bin/python -m evals.answer_quality_eval --judge-model qwen3.5:27b
    venv/bin/python -m evals.answer_quality_eval --only change-fee --show-answers

A judge the same size as the model under test is lenient and noisy; use a
larger --judge-model (or EVAL_JUDGE_MODEL) when you can, and read the
judge's reasons for failures rather than trusting the score blindly.

Exits non-zero when the score (correct = 1, partial = 0.5) is below
--min-score.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.exceptions import OutputParserException
from langchain_core.messages import HumanMessage, ToolMessage
from pydantic import BaseModel, Field, ValidationError

load_dotenv()
# app.db.session needs a URL at import; nothing here opens a connection.
os.environ.setdefault("DATABASE_URL", "postgresql://unused:unused@localhost:5432/unused")

from app.agentic_ai.agents import SPECIALIST_AGENTS  # noqa: E402
from app.agentic_ai.harness.reliability import with_llm_retry  # noqa: E402
from app.agentic_ai.tools import search_faq  # noqa: E402

CASES_FILE = Path(__file__).parent / "answer_quality_cases.jsonl"
AGENTS = {agent.NAME: agent for agent in SPECIALIST_AGENTS}
MAX_AGENT_STEPS = 4
POINTS = {"correct": 1.0, "partial": 0.5, "incorrect": 0.0}

TOOL_NOT_AVAILABLE = (
    "This tool isn't available for this question. Answer from the FAQ "
    "(search_faq), or say you don't have that information."
)

JUDGE_PROMPT = """You are grading an airline support agent's answer to a customer's policy question.

You are given:
- QUESTION: what the customer asked
- REFERENCE: the correct answer, written from the official FAQ
- FAQ TEXT: the FAQ articles the agent retrieved while answering (may be empty)
- ANSWER: the agent's reply

Grade two things independently.

correctness (compare ANSWER to REFERENCE):
- "correct": states the key facts of the REFERENCE (numbers, time limits, conditions) and contradicts none of them. Wording and extra politeness don't matter. If the REFERENCE says the information isn't available, a correct answer says so without inventing a policy.
- "partial": gets the main point right but omits or blurs an important fact or condition (e.g. gives the first bag fee but not the second, or drops "on most fare classes").
- "incorrect": wrong or contradicting facts, answers a different question, refuses when the REFERENCE has an answer, or invents a policy when the REFERENCE says there is none.

grounded (compare ANSWER to FAQ TEXT):
- true if every concrete policy fact in the ANSWER (prices, limits, time windows, rules) appears in the FAQ TEXT, or the ANSWER states no policy facts at all (e.g. "I don't have that information").
- false if the ANSWER states any policy fact that is not in the FAQ TEXT — even a plausible or true-sounding one.

Be strict about numbers and conditions. Give a one or two sentence reason naming the specific fact that decided the grade."""


class Verdict(BaseModel):
    correctness: Literal["correct", "partial", "incorrect"]
    grounded: bool
    reason: str = Field(description="One or two sentences naming the fact that decided the grade")


def make_judge(model: str):
    judge_llm = init_chat_model(
        f"ollama:{model}",
        base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        temperature=0,
        client_kwargs={"timeout": float(os.getenv("OLLAMA_TIMEOUT_S", "60"))},
    )
    return with_llm_retry(
        judge_llm.with_structured_output(Verdict),
        extra_retry_on=(OutputParserException, ValidationError),
    )


def run_agent(agent, question: str) -> tuple[str, list[str], list[str]]:
    """Run the agent loop to a final reply. Returns (answer, FAQ texts
    retrieved, tools called)."""
    messages = [HumanMessage(question)]
    sources: list[str] = []
    tools_called: list[str] = []

    for _ in range(MAX_AGENT_STEPS):
        response = agent.node({"messages": messages})["messages"][0]
        messages.append(response)
        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            return str(response.content), sources, tools_called

        for tc in tool_calls:
            tools_called.append(tc["name"])
            if tc["name"] == "search_faq":
                try:
                    result = search_faq.invoke(tc["args"])
                    sources.append(result)
                except Exception as e:
                    result = f"ERROR: {e!r}"
            else:
                result = TOOL_NOT_AVAILABLE
            messages.append(ToolMessage(result, name=tc["name"], tool_call_id=tc["id"]))

    return f"(no final answer after {MAX_AGENT_STEPS} steps)", sources, tools_called


def judge_answer(judge, case: dict, answer: str, sources: list[str]) -> Verdict:
    faq_text = "\n\n---\n\n".join(sources) if sources else "(the agent retrieved no FAQ text)"
    return judge.invoke(
        [
            {"role": "system", "content": JUDGE_PROMPT},
            {
                "role": "user",
                "content": (
                    f"QUESTION:\n{case['question']}\n\n"
                    f"REFERENCE:\n{case['reference']}\n\n"
                    f"FAQ TEXT:\n{faq_text}\n\n"
                    f"ANSWER:\n{answer}"
                ),
            },
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--judge-model",
        default=os.getenv("EVAL_JUDGE_MODEL") or os.getenv("OLLAMA_MODEL", "qwen3.5:9b"),
        help="Ollama model that grades answers (default: EVAL_JUDGE_MODEL, else OLLAMA_MODEL)",
    )
    parser.add_argument("--min-score", type=float, default=0.75)
    parser.add_argument("--only", help="run a single case by id")
    parser.add_argument("--show-answers", action="store_true", help="print each full answer")
    parser.add_argument("--cases", type=Path, default=CASES_FILE)
    args = parser.parse_args()

    cases = [json.loads(line) for line in args.cases.read_text().splitlines() if line.strip()]
    if args.only:
        cases = [c for c in cases if c["id"] == args.only]
        if not cases:
            print(f"no case with id {args.only!r}")
            return 2

    judge = make_judge(args.judge_model)
    print(f"Judge model: {args.judge_model}\n")

    points = 0.0
    grounded_count = 0
    counts = {"correct": 0, "partial": 0, "incorrect": 0}
    failures = []
    started = time.perf_counter()

    for i, case in enumerate(cases, 1):
        answer, sources, tools_called = run_agent(AGENTS[case["agent"]], case["question"])
        verdict = judge_answer(judge, case, answer, sources)

        points += POINTS[verdict.correctness]
        counts[verdict.correctness] += 1
        grounded_count += verdict.grounded
        ok = verdict.correctness == "correct" and verdict.grounded
        mark = "✓" if ok else ("~" if verdict.correctness == "partial" else "✗")
        grounding = "grounded" if verdict.grounded else "UNGROUNDED"
        searched = "searched FAQ" if "search_faq" in tools_called else "no FAQ search"
        print(f"[{i:>2}/{len(cases)}] {mark} {case['agent']:<8} {case['id']:<26} {verdict.correctness:<9} {grounding:<10} ({searched})")
        if args.show_answers:
            print(f"        Q: {case['question']}\n        A: {answer}\n        judge: {verdict.reason}\n")
        if not ok:
            failures.append((case, answer, verdict))

    elapsed = time.perf_counter() - started
    score = points / len(cases)

    if failures and not args.show_answers:
        print("\nNot fully correct:")
        for case, answer, verdict in failures:
            flat = " ".join(answer.split())
            print(f"  {case['id']} — {verdict.correctness}, {'grounded' if verdict.grounded else 'UNGROUNDED'}")
            print(f"    answer: {flat[:240]}{'…' if len(flat) > 240 else ''}")
            print(f"    judge:  {verdict.reason}")
    print(
        f"\nScore: {score:.0%} · correct {counts['correct']}, partial {counts['partial']}, "
        f"incorrect {counts['incorrect']} · grounded {grounded_count}/{len(cases)} · "
        f"{elapsed / len(cases):.1f}s per case"
    )

    if score < args.min_score:
        print(f"FAIL: below --min-score {args.min_score:.0%}")
        return 1
    print(f"PASS: at or above --min-score {args.min_score:.0%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
