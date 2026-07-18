"""Terminal chat interface for the support agent graph."""

from app.graph import graph


def main() -> None:
    print("Customer Support Agent (type 'exit' or 'quit' to stop)")
    session_id = input("Session ID: ").strip() or "default"
    messages = []
    config = {"configurable": {"thread_id": session_id}}
    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            break

        messages.append({"role": "user", "content": user_input})
        result = graph.invoke({"messages": messages}, config)
        messages = result["messages"]
        print(f"Agent: {messages[-1].content}")


if __name__ == "__main__":
    main()
