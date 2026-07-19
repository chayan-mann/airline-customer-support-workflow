"""Per-query execution tracing: capture the node path a graph run took and
render it as a Mermaid flowchart, using LangGraph's own stream_mode="updates"
(no external tracing service required)."""

from pathlib import Path

TRACE_DIR = Path(__file__).resolve().parent.parent / "traces"


def collect_steps(graph, input_data, config) -> list[tuple[str, dict]]:
    """Run the graph and collect (node_name, node_output) in execution order."""
    steps = []
    for event in graph.stream(input_data, config, stream_mode="updates"):
        steps.extend(event.items())
    return steps


def _summarize_step(node_name: str, node_output: dict) -> str:
    if "intent" in node_output:
        return f"{node_name}: intent={node_output['intent']}"

    messages = node_output.get("messages", [])
    if not messages:
        return node_name

    msg = messages[-1]
    tool_calls = getattr(msg, "tool_calls", None)
    if tool_calls:
        calls = ", ".join(f"{tc['name']}({tc['args']})" for tc in tool_calls)
        return f"{node_name}: requests {calls}"

    content = str(getattr(msg, "content", msg))
    snippet = content if len(content) <= 60 else content[:57] + "..."
    return f"{node_name}: {snippet}"


def render_mermaid(steps: list[tuple[str, dict]]) -> str:
    lines = ["flowchart TD", '    start(["User query"])']
    prev = "start"
    for i, (node_name, node_output) in enumerate(steps):
        node_id = f"n{i}"
        label = _summarize_step(node_name, node_output).replace('"', "'")
        lines.append(f'    {node_id}["{label}"]')
        lines.append(f"    {prev} --> {node_id}")
        prev = node_id
    lines.append(f'    {prev} --> done(["Reply sent"])')
    return "\n".join(lines)


def path_summary(steps: list[tuple[str, dict]]) -> str:
    return " → ".join(node for node, _ in steps)


def save_trace(session_id: str, turn: int, steps: list[tuple[str, dict]]) -> Path:
    TRACE_DIR.mkdir(exist_ok=True)
    path = TRACE_DIR / f"{session_id}_turn{turn}.mmd"
    path.write_text(render_mermaid(steps))
    return path
