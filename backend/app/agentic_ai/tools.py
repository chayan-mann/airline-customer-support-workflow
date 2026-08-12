"""Shared tools available to specialist agents."""

from langchain_core.tools import tool

from app.agentic_ai import knowledge_base


@tool
def search_faq(query: str) -> str:
    """Search the customer support FAQ knowledge base for relevant articles."""
    results = knowledge_base.search(query)
    if not results:
        return "No relevant FAQ articles found."
    return "\n\n".join(doc.page_content for doc in results)
