

import os
from typing import Annotated, Literal

from dotenv import load_dotenv
from typing_extensions import TypedDict
from pydantic import BaseModel
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool

from app.agentic_ai.agents import SPECIALIST_AGENTS, escalation
from app.agentic_ai.llm import llm

load_dotenv()


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
    result = classifier.invoke(messages)
    return {"intent": result.intent}


# build the graph
graph_builder = StateGraph(State)

# add the classifier and one agent+tools pair per specialist agent module
graph_builder.add_node("classify_intent", classify_intent)
for agent in SPECIALIST_AGENTS:
    graph_builder.add_node(f"{agent.NAME}_agent", agent.node)
    graph_builder.add_node(f"{agent.NAME}_tools", ToolNode(agent.TOOLS))
graph_builder.add_node("escalation_agent", escalation.node)

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
    # Pre-built LangGraph logic that reads tool_calls in messages; the path
    # map sends it to this specialist's own tools node instead of a shared one.
    graph_builder.add_conditional_edges(
        f"{agent.NAME}_agent",
        tools_condition,
        {"tools": f"{agent.NAME}_tools", END: END},
    )
    # Connect each specialist's tools node back to that same specialist
    graph_builder.add_edge(f"{agent.NAME}_tools", f"{agent.NAME}_agent")

graph_builder.add_edge("escalation_agent", END)

TOOL_NODE_NAMES = {f"{agent.NAME}_tools" for agent in SPECIALIST_AGENTS}

connection_pool = ConnectionPool(
    conninfo=os.environ["DATABASE_URL"],
    max_size=20,
    kwargs={"autocommit": True, "prepare_threshold": 0},
)
checkpointer = PostgresSaver(connection_pool)
checkpointer.setup()

# Pause right before any "*_tools" node runs so a human can approve/reject
# the pending tool call (e.g. a real delete_database_record or
# charge_credit_card tool) before it actually executes.
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
