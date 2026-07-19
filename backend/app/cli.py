"""Terminal chat interface for the support agent graph."""

from langchain_core.messages import ToolMessage

from app.agentic_ai.graph import TOOL_NODE_NAMES, TOOL_REJECTED_MESSAGE, graph
from app.agentic_ai.tracing import collect_steps, path_summary, save_trace


def _pending_tool_node(config: dict) -> str | None:
    state = graph.get_state(config)
    pending = set(state.next) & TOOL_NODE_NAMES
    return next(iter(pending), None)


def _pending_tool_calls(config: dict) -> list[dict]:
    if _pending_tool_node(config) is None:
        return []
    state = graph.get_state(config)
    return getattr(state.values["messages"][-1], "tool_calls", None) or []


def _handle_approval(config: dict) -> list[tuple[str, dict]]:
    """If the graph is paused on a tool call, ask the human to approve/reject it."""
    steps: list[tuple[str, dict]] = []
    while True:
        pending = _pending_tool_calls(config)
        if not pending:
            return steps

        for tc in pending:
            print(f"Agent wants to call tool: {tc['name']}({tc['args']})")
        decision = input("Approve? [y/N]: ").strip().lower()

        if decision in {"y", "yes"}:
            steps.extend(collect_steps(graph, None, config))
        else:
            rejections = [
                ToolMessage(content=TOOL_REJECTED_MESSAGE, tool_call_id=tc["id"])
                for tc in pending
            ]
            graph.update_state(
                config, {"messages": rejections}, as_node=_pending_tool_node(config)
            )
            steps.extend(collect_steps(graph, None, config))


def main() -> None:
    print("Customer Support Agent (type 'exit' or 'quit' to stop)")
    session_id = input("Session ID: ").strip() or "default"
    config = {"configurable": {"thread_id": session_id}}
    turn = 0
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

        turn += 1
        steps = collect_steps(
            graph, {"messages": [{"role": "user", "content": user_input}]}, config
        )
        steps.extend(_handle_approval(config))

        state = graph.get_state(config)
        print(f"Agent: {state.values['messages'][-1].content}")

        print(f"[trace] {path_summary(steps)}")
        trace_path = save_trace(session_id, turn, steps)
        print(f"Saved flow to {trace_path} — paste into https://mermaid.live to view")


if __name__ == "__main__":
    main()
