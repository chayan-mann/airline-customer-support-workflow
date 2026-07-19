"""Shared chat model used by the intent classifier and all specialist agents."""

import os

from langchain.chat_models import init_chat_model

llm = init_chat_model(
    f"ollama:{os.getenv('OLLAMA_MODEL', 'qwen3.5:9b')}",
    base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
)
