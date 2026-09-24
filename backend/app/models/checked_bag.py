"""SQLAlchemy model for checked bags."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CheckedBag(Base):
    """One row per physical bag checked in for a booking. Most bags have no
    issues (checked_in -> arrived normally) — this table is what makes
    "show me my baggage" meaningful even when nothing's wrong."""

    __tablename__ = "checked_bags"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # ondelete="CASCADE": no ORM relationship()/cascade exists anywhere in
    # this project — without this, cancel_booking raises IntegrityError the
    # first time it's used on a booking that has checked bags.
    booking_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"), index=True)
    tag_number: Mapped[str] = mapped_column(String(10), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20))  # checked_in/in_transit/arrived/delayed/lost/damaged
    weight_kg: Mapped[float | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)
