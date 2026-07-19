from pathlib import Path

from app.agents.booking.tools import change_flight_date, lookup_booking, select_seat
from app.agents.common import build_prompt
from app.llm import llm
from app.tools import search_faq

NAME = "booking"
TOOLS = [search_faq, lookup_booking, change_flight_date, select_seat]
PROMPT = build_prompt(Path(__file__).parent)

_llm_with_tools = llm.bind_tools(TOOLS)


def node(state):
    messages = [{"role": "system", "content": PROMPT}, *state["messages"]]
    return {"messages": [_llm_with_tools.invoke(messages)]}
