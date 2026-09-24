"""Measure how accurately the real model routes messages to specialists.

Runs every labelled message in classifier_cases.jsonl through the production
classify_intent (same prompt, model, retries and fallback) against your
local Ollama. Needs Ollama running; does not need Postgres.

    cd backend
    venv/bin/python -m evals.classifier_eval
    venv/bin/python -m evals.classifier_eval --min-accuracy 0.9

Exits non-zero when accuracy is below --min-accuracy, so it can gate a
prompt or model change.
"""

import argparse
import json
import logging
import sys
import time
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from app.agentic_ai.classifier import classify_intent  # noqa: E402

CASES_FILE = Path(__file__).parent / "classifier_cases.jsonl"


class _FallbackCounter(logging.Handler):
    """Counts classifier_fallback events, so a model that fails to answer
    isn't mistaken for one that correctly answered "general"."""

    def __init__(self):
        super().__init__()
        self.count = 0

    def emit(self, record):
        if '"classifier_fallback"' in record.getMessage():
            self.count += 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--min-accuracy", type=float, default=0.85)
    parser.add_argument("--cases", type=Path, default=CASES_FILE)
    args = parser.parse_args()

    cases = [json.loads(line) for line in args.cases.read_text().splitlines() if line.strip()]

    harness_logger = logging.getLogger("harness")
    fallbacks = _FallbackCounter()
    harness_logger.addHandler(fallbacks)
    # Keep the output readable: fallbacks are counted, not printed per line.
    for handler in list(harness_logger.handlers):
        if isinstance(handler, logging.StreamHandler) and getattr(handler, "stream", None) is sys.stdout:
            harness_logger.removeHandler(handler)

    correct = Counter()
    total = Counter()
    misses = []
    started = time.perf_counter()

    for i, case in enumerate(cases, 1):
        before = fallbacks.count
        predicted = classify_intent({"messages": [{"role": "user", "content": case["message"]}]})["intent"]
        fell_back = fallbacks.count > before

        expected = case["intent"]
        total[expected] += 1
        ok = predicted == expected and not fell_back
        if ok:
            correct[expected] += 1
        else:
            misses.append((case["message"], expected, "fallback→general" if fell_back else predicted))
        print(f"[{i:>2}/{len(cases)}] {'✓' if ok else '✗'} {expected:<9} → {predicted:<9} {case['message']}")

    elapsed = time.perf_counter() - started
    accuracy = sum(correct.values()) / len(cases)

    print("\nPer intent:")
    for intent in sorted(total):
        print(f"  {intent:<9} {correct[intent]}/{total[intent]}")
    if misses:
        print("\nMisses:")
        for message, expected, got in misses:
            print(f"  expected {expected:<9} got {got:<17} {message}")
    print(
        f"\nAccuracy: {accuracy:.0%} ({sum(correct.values())}/{len(cases)}) · "
        f"fallbacks: {fallbacks.count} · {elapsed / len(cases):.1f}s per message"
    )

    if accuracy < args.min_accuracy:
        print(f"FAIL: below --min-accuracy {args.min_accuracy:.0%}")
        return 1
    print(f"PASS: at or above --min-accuracy {args.min_accuracy:.0%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
