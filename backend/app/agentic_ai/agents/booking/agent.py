from pathlib import Path

from app.agentic_ai.agents.booking.tools import change_flight_date, list_my_bookings, select_seat
from app.agentic_ai.agents.common import build_prompt
from app.agentic_ai.llm import llm
from app.agentic_ai.tools import search_faq

NAME = "booking"
TOOLS = [search_faq, list_my_bookings, change_flight_date, select_seat]
PROMPT = build_prompt(Path(__file__).parent)

_llm_with_tools = llm.bind_tools(TOOLS)


def node(state):
    messages = [{"role": "system", "content": PROMPT}, *state["messages"]]
    return {"messages": [_llm_with_tools.invoke(messages)]}
