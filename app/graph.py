

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

load_dotenv()


class State(TypedDict):
    messages: Annotated[list, add_messages]

# define a tool for multiplying two numbers
@tool
def multiply(a: int, b:int) -> int:
    """Multiplies two numbers."""
    return a * b

# Group our tools into a list
tools = [multiply]


llm = init_chat_model(
    f"ollama:{os.getenv('OLLAMA_MODEL', 'llama3.1:8b')}",
    base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
)

# This tells the LLM: "Hey, you are allowed to call these functions"
llm_with_tools = llm.bind_tools(tools)


def chatbot(state: State) -> State:
    # use the tool aware LLM to respond to the user message
    return {"messages": [llm_with_tools.invoke(state["messages"])]}

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
graph = graph_builder.compile(checkpointer=memory)

if __name__ == "__main__":
    # We ask a question that forces the LLM to use our tool
    query = {"messages": [{"role": "user", "content": "What is 143 multiplied by 23?"}]}
    
    print("🚀 Running graph with a math question...\n")
    
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