

import json
import logging
import os
from typing import Annotated, Literal

from dotenv import load_dotenv
from typing_extensions import TypedDict
from pydantic import BaseModel
from langgraph.prebuilt import ToolNode
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool

from app.agentic_ai.agents import SPECIALIST_AGENTS, escalation
from app.agentic_ai.harness.policy import needs_approval, unclassified_tools
from app.agentic_ai.harness.reliability import handle_tool_error
from app.agentic_ai.llm import llm

load_dotenv()

logger = logging.getLogger("harness")


class State(TypedDict):
    messages: Annotated[list, add_messages]
    intent: str
    user_id: str


TOOL_REJECTED_MESSAGE = (
    "REJECTED: A human reviewer denied this tool call. It was NOT executed "
    "and no result exists. Do not compute or guess the answer yourself — "
    "tell the user the action was denied."
)

INTENT_CLASSIFIER_PROMPT = """Classify the user's most recent request into exactly one category:
- booking: booking & reservations, flight changes, check-in, seat selection
- baggage: baggage allowance, lost/delayed/damaged baggage, pet travel
- billing: payment & billing issues, refunds, flight delays & cancellations
- general: travel documents, frequent flyer program, in-flight services, contact info, or plain conversation/chit-chat that isn't a specific support question
- escalate: requests needing a human specialist — wheelchair/accessibility assistance, unaccompanied minors, service animals, or an explicit request to speak with a human

If you are unsure, choose "general" rather than "escalate"."""


class IntentClassification(BaseModel):
    intent: Literal["booking", "baggage", "billing", "general", "escalate"]


def classify_intent(state: State) -> State:
    classifier = llm.with_structured_output(IntentClassification)
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


# build the graph
graph_builder = StateGraph(State)

# Each specialist gets two tool nodes running the same tools: "*_read_tools"
# for read-only batches (runs straight away) and "*_tools" for batches with
# any side effect (paused for human approval, see interrupt_before below).
graph_builder.add_node("classify_intent", classify_intent)
for agent in SPECIALIST_AGENTS:
    if missing := unclassified_tools(agent.TOOLS):
        logger.warning(json.dumps({"event": "unclassified_tools", "agent": agent.NAME, "tools": missing}))
    graph_builder.add_node(f"{agent.NAME}_agent", agent.node)
    graph_builder.add_node(
        f"{agent.NAME}_read_tools", ToolNode(agent.TOOLS, handle_tool_errors=handle_tool_error),
    )
    graph_builder.add_node(
        f"{agent.NAME}_tools", ToolNode(agent.TOOLS, handle_tool_errors=handle_tool_error),
    )
graph_builder.add_node("escalation_agent", escalation.node)


def route_tool_calls(state: State) -> Literal["read", "write", "__end__"]:
    """Like tools_condition, but splits tool calls by risk tier."""
    tool_calls = getattr(state["messages"][-1], "tool_calls", None)
    if not tool_calls:
        return END
    return "write" if needs_approval(tool_calls) else "read"


# connect the nodes
graph_builder.add_edge(START, "classify_intent")

# Route to the specialist matching the classified intent
graph_builder.add_conditional_edges(
    "classify_intent",
    lambda state: state["intent"],
    {agent.NAME: f"{agent.NAME}_agent" for agent in SPECIALIST_AGENTS}
    | {"escalate": "escalation_agent"},
)

for agent in SPECIALIST_AGENTS:
    # The path map sends each batch to this specialist's own tool nodes
    # instead of a shared one.
    graph_builder.add_conditional_edges(
        f"{agent.NAME}_agent",
        route_tool_calls,
        {"read": f"{agent.NAME}_read_tools", "write": f"{agent.NAME}_tools", END: END},
    )
    # Connect both tool nodes back to that same specialist
    graph_builder.add_edge(f"{agent.NAME}_read_tools", f"{agent.NAME}_agent")
    graph_builder.add_edge(f"{agent.NAME}_tools", f"{agent.NAME}_agent")

graph_builder.add_edge("escalation_agent", END)

# Only the side-effect nodes pause for approval; "*_read_tools" never do.
TOOL_NODE_NAMES = {f"{agent.NAME}_tools" for agent in SPECIALIST_AGENTS}

connection_pool = ConnectionPool(
    conninfo=os.environ["DATABASE_URL"],
    max_size=20,
    kwargs={"autocommit": True, "prepare_threshold": 0},
)
checkpointer = PostgresSaver(connection_pool)
checkpointer.setup()

# Pause right before any side-effect "*_tools" node (not "*_read_tools") runs
# so a human can approve/reject the pending tool call (e.g. create_booking or
# cancel_booking) before it actually executes.
graph = graph_builder.compile(
    checkpointer=checkpointer, interrupt_before=list(TOOL_NODE_NAMES)
)

if __name__ == "__main__":
    # We ask a question that forces the LLM to use our tool
    query = {"messages": [{"role": "user", "content": "What is your return policy?"}]}
    config = {"configurable": {"thread_id": "demo"}}

    print("🚀 Running graph with a support question...\n")

    for event in graph.stream(query, config, stream_mode="updates"):
        for node_name, node_output in event.items():
            print(f"📍 Node '{node_name}' just executed.")
            latest_msg = node_output["messages"][-1]

            # Check if it's a tool call or final text response
            if hasattr(latest_msg, 'tool_calls') and latest_msg.tool_calls:
                print(f"🤖 LLM requested a tool call: {latest_msg.tool_calls}\n")
            else:
                print(f"📝 Output content: {latest_msg.content}\n")
            print("-" * 50)
