"""SQLAlchemy model for ticket payments."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Payment(Base):
    """What was charged for one booking.

    Outlives its booking on purpose: cancel_booking deletes the Booking row,
    and the payment is exactly what a refund needs afterwards. So booking_id
    is SET NULL on delete (NULL means "booking was cancelled"), and the
    confirmation code and flight summary are snapshotted here.
    """

    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    reference: Mapped[str] = mapped_column(String(10), unique=True, index=True)  # e.g. "PY7K2X9Q"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    booking_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("bookings.id", ondelete="SET NULL"), index=True, default=None
    )
    confirmation_code: Mapped[str] = mapped_column(String(10), index=True)
    description: Mapped[str] = mapped_column(String(200))  # e.g. "AI101 DEL→BOM on 2026-08-14"
    base_fare: Mapped[float]
    taxes_fees: Mapped[float]
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    method: Mapped[str] = mapped_column(String(50))  # e.g. "Visa ending 4242"
    is_refundable: Mapped[bool]
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    @property
    def total(self) -> float:
        return round(self.base_fare + self.taxes_fees, 2)

    @property
    def booking_cancelled(self) -> bool:
        return self.booking_id is None
