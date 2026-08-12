"""SQLAlchemy model for short-lived, single-use tokens proving a booking-flow
step (picking an alternative flight) actually happened server-side, so a
later step can't be invoked with a flight the LLM made up."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class FlightSelectionToken(Base):
    __tablename__ = "flight_selection_tokens"

    # Short opaque id (e.g. "opt_a1b2c3d4"), not a UUID — kept short since the
    # LLM has to echo it back verbatim in a later tool call; a long token is
    # more likely to get mangled in transit.
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    booking_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bookings.id"), index=True)
    flight_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("flights.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)