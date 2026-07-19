

import os
from pathlib import Path
from typing import Annotated, Literal

from dotenv import load_dotenv
from typing_extensions import TypedDict
from pydantic import BaseModel
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain.chat_models import init_chat_model
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool

from app import knowledge_base

load_dotenv()


class State(TypedDict):
    messages: Annotated[list, add_messages]
    intent: str

# define a tool for searching the customer support FAQ knowledge base
@tool
def search_faq(query: str) -> str:
    """Search the customer support FAQ knowledge base for relevant articles."""
    results = knowledge_base.search(query)
    if not results:
        return "No relevant FAQ articles found."
    return "\n\n".join(doc.page_content for doc in results)

# Group our tools into a list
tools = [search_faq]


llm = init_chat_model(
    f"ollama:{os.getenv('OLLAMA_MODEL', 'qwen3.5:9b')}",
    base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
)

# This tells the LLM: "Hey, you are allowed to call these functions"
llm_with_tools = llm.bind_tools(tools)


PROMPTS_DIR = Path(__file__).parent / "prompts"
COMMON_RULES = (PROMPTS_DIR / "system_prompt.md").read_text().strip()

# One topic-scope file per specialist; combined with the shared behavioral
# rules above so those rules aren't duplicated across every specialist prompt.
SPECIALIST_TOPIC_FILES = {
    "booking": "booking_topics.md",
    "baggage": "baggage_topics.md",
    "billing": "billing_topics.md",
    "general": "general_topics.md",
}

SPECIALIST_PROMPTS = {
    name: f"{(PROMPTS_DIR / filename).read_text().strip()}\n\n{COMMON_RULES}"
    for name, filename in SPECIALIST_TOPIC_FILES.items()
}

TOOL_REJECTED_MESSAGE = (
    "REJECTED: A human reviewer denied this tool call. It was NOT executed "
    "and no result exists. Do not compute or guess the answer yourself — "
    "tell the user the action was denied."
)

ESCALATION_MESSAGE = (
    "This request needs a human specialist to help you safely — connecting "
    "you with a live agent now. Please hold."
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


def make_specialist_node(prompt: str):
    """Build a node function bound to a specialist's system prompt."""

    def node(state: State) -> State:
        messages = [{"role": "system", "content": prompt}, *state["messages"]]
        return {"messages": [llm_with_tools.invoke(messages)]}

    return node


def escalation_agent(state: State) -> State:
    return {"messages": [{"role": "assistant", "content": ESCALATION_MESSAGE}]}


# build the graph
graph_builder = StateGraph(State)

# add the classifier and one agent+tools pair per specialist
graph_builder.add_node("classify_intent", classify_intent)
for name, prompt in SPECIALIST_PROMPTS.items():
    graph_builder.add_node(f"{name}_agent", make_specialist_node(prompt))
    graph_builder.add_node(f"{name}_tools", ToolNode(tools))
graph_builder.add_node("escalation_agent", escalation_agent)

# connect the nodes
graph_builder.add_edge(START, "classify_intent")

# Route to the specialist matching the classified intent
graph_builder.add_conditional_edges(
    "classify_intent",
    lambda state: state["intent"],
    {
        "booking": "booking_agent",
        "baggage": "baggage_agent",
        "billing": "billing_agent",
        "general": "general_agent",
        "escalate": "escalation_agent",
    },
)

for name in SPECIALIST_PROMPTS:
    # Pre-built LangGraph logic that reads tool_calls in messages; the path
    # map sends it to this specialist's own tools node instead of a shared one.
    graph_builder.add_conditional_edges(
        f"{name}_agent",
        tools_condition,
        {"tools": f"{name}_tools", END: END},
    )
    # Connect each specialist's tools node back to that same specialist
    graph_builder.add_edge(f"{name}_tools", f"{name}_agent")

graph_builder.add_edge("escalation_agent", END)

TOOL_NODE_NAMES = {f"{name}_tools" for name in SPECIALIST_PROMPTS}

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
