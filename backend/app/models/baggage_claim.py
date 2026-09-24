"""SQLAlchemy model for baggage claims."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BaggageClaim(Base):
    """A customer-filed issue against a specific checked bag."""

    __tablename__ = "baggage_claims"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    claim_number: Mapped[str] = mapped_column(String(10), unique=True, index=True)  # e.g. "BG4F7K2X"
    checked_bag_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("checked_bags.id", ondelete="CASCADE"), index=True)
    # Denormalized from checked_bag -> booking -> user_id, same pattern as
    # FlightSelectionToken.user_id — avoids a double join for ownership checks.
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    claim_type: Mapped[str] = mapped_column(String(20))  # lost/delayed/damaged
    description: Mapped[str] = mapped_column(String(2000))
    status: Mapped[str] = mapped_column(String(20), default="open")  # open/investigating/resolved
    # Informational/status-tracking only — NOT wired to billing/payment.
    compensation_amount: Mapped[float | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(default=None)
