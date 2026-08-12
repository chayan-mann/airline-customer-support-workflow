"""SQLAlchemy model for a flight's seat map.

Each row represents one physical seat that exists on a given flight. This is
the flight's *capacity* — the set of valid seat numbers. Occupancy is not
tracked here; a seat is taken if a Booking references the same
(flight_id, seat_number) pair (Booking has a matching unique constraint).
"""

import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Seat(Base):
    __tablename__ = "seats"
    __table_args__ = (UniqueConstraint("flight_id", "seat_number", name="uq_seat_flight_number"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    flight_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("flights.id"), index=True)
    seat_number: Mapped[str] = mapped_column(String(4))
