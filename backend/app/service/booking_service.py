import uuid
import logging
import secrets
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.models import Booking, Flight, Seat, FlightSelectionToken

from datetime import datetime, timedelta, timezone

TOKEN_TTL_MINUTES = 10

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


# function to generate a unique flight selection token
def _generate_token_id(db: Session) -> str:
    for _ in range(5):
        token_id = "opt_" + secrets.token_hex(4)
        if db.get(FlightSelectionToken, token_id) is None:
            return token_id
    raise RuntimeError("Failed to generate a unique flight selection token after 5 attempts.")

# function to validate a flight selection token
def _resolve_flight_token(db: Session, user_id: uuid.UUID, token_id: str) -> FlightSelectionToken:
    """Validate a token without consuming it — safe to check repeatedly (e.g. list_available_seats followed by a retried move_booking)."""

    token = db.get(FlightSelectionToken, token_id)

    if token is None or token.user_id != user_id:
        raise BookingError("That flight option is invalid. Call find_alternative_flights again.")
    
    if token.consumed_at is not None:
        raise BookingError("That flight option has already been used. Call find_alternative_flights again for current options.")
    
    if token.expires_at < datetime.now(timezone.utc):
        raise BookingError("That flight option has expired. Call find_alternative_flights again for current options.")
    
    return token


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


def list_available_seats_for_token(
    db: Session, user_id: uuid.UUID, token_id: str
) -> tuple[Flight, list[str]]:
    """Available seats on the flight named by a flight-selection token."""
    token = _resolve_flight_token(db, user_id, token_id)
    flight = db.get(Flight, token.flight_id)
    return flight, list_available_seats(db, flight.id)  # existing helper, unchanged


def list_alternative_flights(
    db: Session, user_id: uuid.UUID, confirmation_code: str
) -> tuple[Booking, Flight, list[tuple[str, Flight]]]:
    """A booking's current flight, plus other same-route flights, each paired
    with a single-use token proving this exact option was legitimately
    offered — move_booking requires one of these tokens, never a bare
    flight_number/date, so it can't be called with a fabricated flight."""

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

    expires_at = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_TTL_MINUTES)
    options: list[tuple[str, Flight]] = []
    for flight in alternatives:
        token_id = _generate_token_id(db)
        db.add(FlightSelectionToken(
            id=token_id,
            user_id=user_id,
            booking_id=booking.id,
            flight_id=flight.id,
            expires_at=expires_at)
        )
        options.append((token_id, flight))
    db.commit()
    # expire_on_commit expired every object this session touched — booking,
    # current_flight, and each alternative flight — so all need refreshing
    # before the caller can safely read their attributes after closing the
    # session (same issue as move_booking below).
    db.refresh(booking)
    db.refresh(current_flight)
    for _, flight in options:
        db.refresh(flight)

    return booking, current_flight, options


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
    db: Session, user_id: uuid.UUID, confirmation_code: str, flight_option_token: str, new_seat: str
) -> tuple[Booking, Flight]:
    """Move a booking to the flight named by a flight-selection token, and a
    seat on it — freeing the old seat. Never accepts a flight_number/date
    directly; the token (from list_alternative_flights) is the only way to
    name the target flight, so this can't be called with a fabricated one.
    """
    booking, current_flight = _get_owned_booking(db, user_id, confirmation_code)
    token = _resolve_flight_token(db, user_id, flight_option_token)
    if token.booking_id != booking.id:
        raise BookingError("That flight option doesn't belong to this booking. Call find_alternative_flights again.")

    new_flight = db.get(Flight, token.flight_id)
    if new_flight.origin != current_flight.origin or new_flight.destination != current_flight.destination:
        # Defense in depth — tokens are only ever issued for same-route
        # flights by construction, so this should be unreachable.
        raise BookingError("That flight isn't on the same route as this booking.")

    new_seat = new_seat.strip().upper()
    _validate_seat_available(db, new_flight.id, new_seat)

    booking.flight_id = new_flight.id
    booking.seat = new_seat
    token.consumed_at = datetime.now(timezone.utc)
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

