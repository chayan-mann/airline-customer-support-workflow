import uuid
import logging
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.models import Booking, Flight, Seat

def list_bookings_for_user(db:Session, user_id: uuid.UUID) -> list[tuple[Booking, Flight]]:
    """"Returns all the flight bookings for a given user, along with the associated flight details."""
    return (
        db.query(Booking, Flight)
        .join(Flight, Booking.flight_id == Flight.id)
        .filter(Booking.user_id == user_id)
        .order_by(Flight.date.desc())
        .all()
    )


class BookingError(Exception):
    """A user-facing error from a booking operation (not found, seat taken, etc.)."""


def _get_owned_booking(db: Session, user_id: uuid.UUID, confirmation_code: str) -> tuple[Booking, Flight]:
    """Look up a booking by confirmation code, scoped to the given user.

    Raises BookingError if there's no match — whether the code doesn't exist
    or belongs to someone else. Callers must not distinguish the two cases
    in any user-facing message.
    """
    row = (
        db.query(Booking, Flight)
        .join(Flight, Booking.flight_id == Flight.id)
        .filter(
            Booking.confirmation_code == confirmation_code.strip().upper(),
            Booking.user_id == user_id,
        )
        .first()
    )
    if row is None:
        raise BookingError(f"No booking found for confirmation code {confirmation_code!r}.")
    return row


def _sort_seat_numbers(seat_numbers: list[str]) -> list[str]:
    """Sort seat labels like '2A', '14C' numerically by row, not lexically."""
    def key(seat_number: str) -> tuple[int, str]:
        i = 0
        while i < len(seat_number) and seat_number[i].isdigit():
            i += 1
        return (int(seat_number[:i]), seat_number[i:])
    return sorted(seat_numbers, key=key)


def list_alternative_flights(
    db: Session, user_id: uuid.UUID, confirmation_code: str
) -> tuple[Booking, Flight, list[Flight]]:
    """A booking's current flight, plus other flights on the same route (excluding itself)."""
    booking, current_flight = _get_owned_booking(db, user_id, confirmation_code)
    alternatives = (
        db.query(Flight)
        .filter(
            Flight.origin == current_flight.origin,
            Flight.destination == current_flight.destination,
            Flight.id != current_flight.id,
        )
        .order_by(Flight.date, Flight.departure_time)
        .all()
    )
    return booking, current_flight, alternatives


def get_flight_by_number_date(db: Session, flight_number: str, date: str) -> Flight | None:
    """Resolve a flight the LLM referenced by number+date (never a raw UUID)."""
    return (
        db.query(Flight)
        .filter(Flight.flight_number == flight_number.strip().upper(), Flight.date == date)
        .first()
    )


def list_available_seats(db: Session, flight_id: uuid.UUID) -> list[str]:
    """Seat numbers on this flight not already claimed by any booking."""
    all_seats = {s.seat_number for s in db.query(Seat).filter(Seat.flight_id == flight_id)}
    taken = {b.seat for b in db.query(Booking).filter(Booking.flight_id == flight_id)}
    return _sort_seat_numbers(list(all_seats - taken))


def _validate_seat_available(db: Session, flight_id: uuid.UUID, seat_number: str) -> None:
    exists = (
        db.query(Seat)
        .filter(Seat.flight_id == flight_id, Seat.seat_number == seat_number)
        .first()
    )
    if exists is None:
        raise BookingError(f"Seat {seat_number!r} does not exist on that flight.")

    taken = (
        db.query(Booking)
        .filter(Booking.flight_id == flight_id, Booking.seat == seat_number)
        .first()
    )
    if taken is not None:
        raise BookingError(f"Seat {seat_number!r} is already taken on that flight.")


def move_booking(
    db: Session,
    user_id: uuid.UUID,
    confirmation_code: str,
    new_flight_number: str,
    new_date: str,
    new_seat: str,
) -> tuple[Booking, Flight]:
    """Move a booking to a different flight and seat, freeing its old seat.

    The new flight is identified by (flight_number, date) rather than its
    internal id, since that's the only reference the LLM ever sees — the
    alternatives list from list_alternative_flights() shows flight numbers
    and dates, never UUIDs.
    """
    booking, current_flight = _get_owned_booking(db, user_id, confirmation_code)
    new_flight = (
        db.query(Flight)
        .filter(Flight.flight_number == new_flight_number.strip().upper(), Flight.date == new_date)
        .first()
    )
    if new_flight is None:
        raise BookingError(f"No flight {new_flight_number!r} found on {new_date}.")

    if new_flight.origin != current_flight.origin or new_flight.destination != current_flight.destination:
        raise BookingError("The selected flight isn't on the same route as your current booking.")

    new_seat = new_seat.strip().upper()
    _validate_seat_available(db, new_flight.id, new_seat)

    booking.flight_id = new_flight.id
    booking.seat = new_seat
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise BookingError(f"Seat {new_seat!r} was just taken by someone else — please pick another.")
    # expire_on_commit (the sessionmaker default) expired every object this
    # session touched, including new_flight — both need refreshing so their
    # attributes are safe to read after the caller closes the session.
    db.refresh(booking)
    db.refresh(new_flight)
    return booking, new_flight


def update_seat(
    db: Session, user_id: uuid.UUID, confirmation_code: str, new_seat: str
) -> tuple[Booking, Flight]:
    """Change a booking's seat on its current flight."""
    booking, flight = _get_owned_booking(db, user_id, confirmation_code)
    new_seat = new_seat.strip().upper()
    _validate_seat_available(db, booking.flight_id, new_seat)

    booking.seat = new_seat
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise BookingError(f"Seat {new_seat!r} was just taken by someone else — please pick another.")
    db.refresh(booking)
    db.refresh(flight)
    return booking, flight

