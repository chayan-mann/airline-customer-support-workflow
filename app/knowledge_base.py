"""Mock customer support FAQ knowledge base with in-memory vector search."""

import os

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_ollama import OllamaEmbeddings

load_dotenv()

FAQ_DOCS = [
    Document(
        page_content=(
            "Shipping & Delivery: Standard shipping takes 3-5 business days. "
            "Express shipping takes 1-2 business days. Orders placed before "
            "2pm ET ship the same day. We currently ship within the US and "
            "Canada only."
        ),
        metadata={"topic": "shipping"},
    ),
    Document(
        page_content=(
            "Order Tracking: Once your order ships, you'll receive a "
            "confirmation email with a tracking number and link. You can "
            "also track your order anytime by logging into your account and "
            "visiting the 'My Orders' page."
        ),
        metadata={"topic": "order_tracking"},
    ),
    Document(
        page_content=(
            "Returns Policy: Items can be returned within 30 days of "
            "delivery for a full refund, as long as they are unused and in "
            "original packaging. Final sale items and gift cards are not "
            "eligible for return."
        ),
        metadata={"topic": "returns"},
    ),
    Document(
        page_content=(
            "Refunds: Refunds are issued to the original payment method "
            "within 5-7 business days after we receive and inspect the "
            "returned item. You'll get an email confirmation once the "
            "refund is processed."
        ),
        metadata={"topic": "refunds"},
    ),
    Document(
        page_content=(
            "Order Cancellations: Orders can be cancelled free of charge "
            "within 1 hour of placing them, as long as they haven't already "
            "shipped. After that window, you'll need to wait for delivery "
            "and start a return instead."
        ),
        metadata={"topic": "cancellations"},
    ),
    Document(
        page_content=(
            "Payment Methods: We accept Visa, Mastercard, American Express, "
            "Discover, PayPal, and Apple Pay. We do not currently support "
            "installment or buy-now-pay-later options."
        ),
        metadata={"topic": "billing"},
    ),
    Document(
        page_content=(
            "Billing Issues: If you see a duplicate or incorrect charge, "
            "it's often a temporary authorization hold that will clear "
            "within a few business days. If a charge doesn't clear after 5 "
            "business days, contact support with your order number."
        ),
        metadata={"topic": "billing"},
    ),
    Document(
        page_content=(
            "Password Reset: To reset your password, click 'Forgot "
            "password?' on the login page and enter your account email. "
            "You'll receive a reset link valid for 24 hours. If you don't "
            "see the email, check your spam folder."
        ),
        metadata={"topic": "account"},
    ),
    Document(
        page_content=(
            "Account Management: You can update your email, shipping "
            "addresses, and saved payment methods anytime from the "
            "'Account Settings' page after logging in."
        ),
        metadata={"topic": "account"},
    ),
    Document(
        page_content=(
            "Contact & Business Hours: Our support team is available "
            "Monday-Friday, 9am-6pm ET, via chat and email. Average email "
            "response time is under 24 hours on business days."
        ),
        metadata={"topic": "contact"},
    ),
]

embeddings = OllamaEmbeddings(
    model=os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text"),
    base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
)

vector_store = InMemoryVectorStore(embeddings)
vector_store.add_documents(FAQ_DOCS)


def search(query: str, k: int = 3) -> list[Document]:
    """Return the k most relevant FAQ documents for the given query."""
    return vector_store.similarity_search(query, k=k)
