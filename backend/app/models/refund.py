"""SQLAlchemy model for refunds."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Refund(Base):
    """A refund requested against a payment, after its booking was cancelled."""

    __tablename__ = "refunds"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    refund_number: Mapped[str] = mapped_column(String(10), unique=True, index=True)  # e.g. "RF4F7K2X"
    payment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payments.id", ondelete="CASCADE"), index=True)
    # Denormalized from payment -> user_id, same pattern as BaggageClaim.user_id.
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    amount: Mapped[float]
    # "original_payment" for refundable tickets, "travel_credit" for
    # non-refundable ones (see the Refunds FAQ article).
    refund_to: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="requested")  # requested/processing/completed/rejected
    reason: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(default=None)
