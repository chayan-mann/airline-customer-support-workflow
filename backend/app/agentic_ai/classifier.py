"""Intent classifier: the graph's first node, routing each message to one
specialist agent. Kept out of graph.py so it can be imported (and evaluated
against the real model) without building the graph or touching Postgres."""

import json
import logging
from typing import Literal

from langchain_core.exceptions import OutputParserException
from pydantic import BaseModel, ValidationError

from app.agentic_ai.harness.reliability import with_llm_retry
from app.agentic_ai.llm import llm

logger = logging.getLogger("harness")

INTENT_CLASSIFIER_PROMPT = """Classify the user's most recent request into exactly one category:
- booking: booking & reservations, flight changes, check-in, seat selection
- baggage: baggage allowance, lost/delayed/damaged baggage, pet travel
- billing: payment & billing issues, refunds, flight delays & cancellations
- general: travel documents, frequent flyer program, in-flight services, contact info, or plain conversation/chit-chat that isn't a specific support question
- escalate: requests needing a human specialist — wheelchair/accessibility assistance, unaccompanied minors, service animals, or an explicit request to speak with a human

If you are unsure, choose "general" rather than "escalate"."""


class IntentClassification(BaseModel):
    intent: Literal["booking", "baggage", "billing", "general", "escalate"]


def classify_intent(state: dict) -> dict:
    # Also retry malformed structured output — a fresh sample from a small
    # local model often parses fine — before falling back to "general".
    classifier = with_llm_retry(
        llm.with_structured_output(IntentClassification),
        extra_retry_on=(OutputParserException, ValidationError),
    )
    messages = [
        {"role": "system", "content": INTENT_CLASSIFIER_PROMPT},
        *state["messages"],
    ]
    try:
        result = classifier.invoke(messages)
        return {"intent": result.intent}
    except Exception as e:
        # Small local models sometimes return malformed structured output (or
        # Ollama hiccups); route to the general agent rather than crash the turn.
        logger.warning(json.dumps({"event": "classifier_fallback", "error": repr(e)[:200]}))
        return {"intent": "general"}
