from pathlib import Path

from app.agentic_ai.agents.billing.tools import (
    check_refund_status,
    get_invoice,
    list_my_payments,
    request_refund,
)
from app.agentic_ai.agents.common import build_prompt
from app.agentic_ai.harness.reliability import with_llm_retry
from app.agentic_ai.llm import llm
from app.agentic_ai.tools import search_faq

NAME = "billing"
TOOLS = [search_faq, list_my_payments, get_invoice, request_refund, check_refund_status]
PROMPT = build_prompt(Path(__file__).parent)

_llm_with_tools = with_llm_retry(llm.bind_tools(TOOLS))


def node(state):
    messages = [{"role": "system", "content": PROMPT}, *state["messages"]]
    return {"messages": [_llm_with_tools.invoke(messages)]}
