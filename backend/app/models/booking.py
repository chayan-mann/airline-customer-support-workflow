"""SQLAlchemy model for bookings."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    confirmation_code: Mapped[str] = mapped_column(String(10), unique=True, index=True)
    passenger_name: Mapped[str] = mapped_column(String(200))
    seat: Mapped[str] = mapped_column(String(4))
    status: Mapped[str] = mapped_column(String(20))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    flight_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("flights.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
