from pathlib import Path

from app.agentic_ai.agents.booking.tools import (
    create_booking,
    find_alternative_flights,
    list_available_seats,
    list_my_bookings,
    move_booking,
    search_flights,
    select_seat,
)
from app.agentic_ai.agents.common import build_prompt
from app.agentic_ai.llm import llm
from app.agentic_ai.tools import search_faq

NAME = "booking"
TOOLS = [
    search_faq,
    list_my_bookings,
    find_alternative_flights,
    list_available_seats,
    move_booking,
    select_seat,
    search_flights,
    create_booking,
]
PROMPT = build_prompt(Path(__file__).parent)

_llm_with_tools = llm.bind_tools(TOOLS)


def node(state):
    messages = [{"role": "system", "content": PROMPT}, *state["messages"]]
    return {"messages": [_llm_with_tools.invoke(messages)]}
