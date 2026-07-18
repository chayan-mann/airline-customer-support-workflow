

import os
from typing import Annotated

from dotenv import load_dotenv
from typing_extensions import TypedDict
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain.chat_models import init_chat_model
from langgraph.checkpoint.memory import MemorySaver

from app import knowledge_base

load_dotenv()


class State(TypedDict):
    messages: Annotated[list, add_messages]

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


SYSTEM_PROMPT = (
    "You are a helpful customer support agent. You have access to a "
    "'search_faq' tool that searches our FAQ knowledge base (shipping, "
    "returns, refunds, billing, account, cancellations, contact info). "
    "Call it whenever the user asks a support, policy, or how-to question. "
    "Answer only using the retrieved FAQ content — if it says no relevant "
    "articles were found, tell the user you don't have that information "
    "rather than guessing or inventing policy. For plain conversational "
    "messages that aren't support questions, respond directly without "
    "calling the tool. If a tool call result says it was rejected by a "
    "human reviewer, you must NOT answer using guessed or invented "
    "information. Tell the user plainly that the search was denied and "
    "was not carried out."
)

TOOL_REJECTED_MESSAGE = (
    "REJECTED: A human reviewer denied this tool call. It was NOT executed "
    "and no result exists. Do not compute or guess the answer yourself — "
    "tell the user the action was denied."
)


def chatbot(state: State) -> State:
    # use the tool aware LLM to respond to the user message
    messages = state["messages"]
    first_role = getattr(messages[0], "type", None) if messages else None
    if first_role != "system":
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, *messages]
    return {"messages": [llm_with_tools.invoke(messages)]}

# build the graph
graph_builder = StateGraph(State)

# add the nodes 
graph_builder.add_node("chatbot", chatbot)
graph_builder.add_node("tools", ToolNode(tools))

# connect the nodes 
graph_builder.add_edge(START, "chatbot")


# The Magic: Add a Conditional Edge!
# This checks the LLM's response. If the LLM wants to call a tool, it routes to "tools".
graph_builder.add_conditional_edges(
    "chatbot",
    tools_condition, # Pre-built LangGraph logic that reads tool_calls in messages
)

# Connect the tools node back to the chatbot so it can read the tool results
graph_builder.add_edge("tools", "chatbot")

# graph_builder.add_edge("chatbot", END)

memory = MemorySaver()

# Pause right before the "tools" node runs so a human can approve/reject
# the pending tool call (e.g. a real delete_database_record or
# charge_credit_card tool) before it actually executes.
graph = graph_builder.compile(checkpointer=memory, interrupt_before=["tools"])

if __name__ == "__main__":
    # We ask a question that forces the LLM to use our tool
    query = {"messages": [{"role": "user", "content": "What is your return policy?"}]}

    print("🚀 Running graph with a support question...\n")
    
    for event in graph.stream(query, stream_mode="updates"):
        for node_name, node_output in event.items():
            print(f"📍 Node '{node_name}' just executed.")
            latest_msg = node_output["messages"][-1]
            
            # Check if it's a tool call or final text response
            if hasattr(latest_msg, 'tool_calls') and latest_msg.tool_calls:
                print(f"🤖 LLM requested a tool call: {latest_msg.tool_calls}\n")
            else:
                print(f"📝 Output content: {latest_msg.content}\n")
            print("-" * 50)