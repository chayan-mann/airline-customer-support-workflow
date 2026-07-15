"""Stage 1: Basic Chatbot Graph.

START -> chatbot -> END
"""

import os
from typing import Annotated

from dotenv import load_dotenv
from typing_extensions import TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain.chat_models import init_chat_model

load_dotenv()


class State(TypedDict):
    messages: Annotated[list, add_messages]


llm = init_chat_model(
    f"ollama:{os.getenv('OLLAMA_MODEL', 'llama3.1:8b')}",
    base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
)


def chatbot(state: State) -> State:
    return {"messages": [llm.invoke(state["messages"])]}


graph_builder = StateGraph(State)
graph_builder.add_node("chatbot", chatbot)
graph_builder.add_edge(START, "chatbot")
graph_builder.add_edge("chatbot", END)

graph = graph_builder.compile()


if __name__ == "__main__":
    for event in graph.stream({"messages": [{"role": "user", "content": "Hello!"}]}):
        for value in event.values():
            print(value["messages"][-1].content)
