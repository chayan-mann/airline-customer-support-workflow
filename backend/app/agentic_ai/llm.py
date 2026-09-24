"""Shared chat model used by the intent classifier and all specialist agents."""

import os

from langchain.chat_models import init_chat_model

llm = init_chat_model(
    f"ollama:{os.getenv('OLLAMA_MODEL', 'qwen3.5:9b')}",
    base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
    # Per-request HTTP timeout, so a hung Ollama fails (and gets retried —
    # see harness.reliability.with_llm_retry) instead of blocking forever.
    client_kwargs={"timeout": float(os.getenv("OLLAMA_TIMEOUT_S", "60"))},
)
