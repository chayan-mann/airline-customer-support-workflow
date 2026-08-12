import uuid
import logging
from sqlalchemy.orm import Session
from app.models import Booking, Flight

def list_bookings_for_user(db:Session, user_id: uuid.UUID) -> list[tuple[Booking, Flight]]:
    """"Returns all the flight bookings for a given user, along with the associated flight details."""
    return (
        db.query(Booking, Flight)
        .join(Flight, Booking.flight_id == Flight.id)
        .filter(Booking.user_id == user_id)
        .order_by(Flight.date.desc())
        .all()
    )

