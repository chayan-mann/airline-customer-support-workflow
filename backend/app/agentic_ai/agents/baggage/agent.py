from pathlib import Path

from app.agentic_ai.agents.baggage.tools import (
    check_claim_status,
    list_my_baggage,
    report_baggage_issue,
    track_bag,
)
from app.agentic_ai.agents.common import build_prompt
from app.agentic_ai.llm import llm
from app.agentic_ai.tools import search_faq

NAME = "baggage"
TOOLS = [search_faq, list_my_baggage, track_bag, report_baggage_issue, check_claim_status]
PROMPT = build_prompt(Path(__file__).parent)

_llm_with_tools = llm.bind_tools(TOOLS)


def node(state):
    messages = [{"role": "system", "content": PROMPT}, *state["messages"]]
    return {"messages": [_llm_with_tools.invoke(messages)]}
