"""Shared helpers for building specialist agent prompts."""

from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
COMMON_RULES = (_PROMPTS_DIR / "system_prompt.md").read_text().strip()


def build_prompt(agent_dir: Path) -> str:
    """Combine an agent's topic-scope file with the shared behavioral rules."""
    topic_text = (agent_dir / "prompt.md").read_text().strip()
    return f"{topic_text}\n\n{COMMON_RULES}"
