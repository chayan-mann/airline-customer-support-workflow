"""Booking action tools with structured (Pydantic) inputs."""

import uuid
from typing import Annotated

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState
from pydantic import BaseModel, Field

from app.db.session import SessionLocal
from app.service import booking_service
from app.service.booking_service import BookingError


@tool
def list_my_bookings(user_id: Annotated[str, InjectedState("user_id")]) -> str:
    """List all bookings belonging to the current user."""
    db = SessionLocal()
    try:
        results = booking_service.list_bookings_for_user(db, uuid.UUID(user_id))
    finally:
        db.close()

    if not results:
        return "You have no bookings on file."

    return "\n".join(
        f"Booking {booking.confirmation_code}: {booking.passenger_name} on flight "
        f"{flight.flight_number} from {flight.origin} to {flight.destination} "
        f"on {flight.date} at {flight.departure_time}, seat {booking.seat}. Status: {booking.status}."
        for booking, flight in results
    )


class ConfirmationCodeInput(BaseModel):
    confirmation_code: str = Field(description="The booking confirmation code, e.g. ABC123")


@tool(args_schema=ConfirmationCodeInput)
def find_alternative_flights(
    confirmation_code: str,
    user_id: Annotated[str, InjectedState("user_id")],
) -> str:
    """Find other flights on the same route as an existing booking, to change its date/time.

    Call this first when the user wants to change their flight date — it shows what's
    available. Follow up with list_available_seats once they pick a flight, then
    move_booking to complete the change.
    """
    db = SessionLocal()
    try:
        booking, current_flight, alternatives = booking_service.list_alternative_flights(
            db, uuid.UUID(user_id), confirmation_code
        )
    except BookingError as e:
        return str(e)
    finally:
        db.close()

    header = (
        f"Booking {booking.confirmation_code} is currently on {current_flight.flight_number} "
        f"from {current_flight.origin} to {current_flight.destination} on {current_flight.date} "
        f"at {current_flight.departure_time}, seat {booking.seat}."
    )
    if not alternatives:
        return f"{header} No other flights are available on this route."

    options = "\n".join(f"- {f.flight_number} on {f.date} at {f.departure_time}" for f in alternatives)
    return f"{header}\n\nOther available flights on this route:\n{options}"


class ListSeatsInput(BaseModel):
    flight_number: str = Field(description="The flight number to check seats for, e.g. AI205")
    date: str = Field(description="The flight's date, e.g. 2026-08-14")


@tool(args_schema=ListSeatsInput)
def list_available_seats(flight_number: str, date: str) -> str:
    """List available seats on a specific flight (by flight number and date).

    Call this after find_alternative_flights, once the user has picked a candidate
    flight, to show seat options before completing the change with move_booking.
    """
    db = SessionLocal()
    try:
        flight = booking_service.get_flight_by_number_date(db, flight_number, date)
        if flight is None:
            return f"No flight {flight_number!r} found on {date}."
        seats = booking_service.list_available_seats(db, flight.id)
    finally:
        db.close()

    if not seats:
        return f"No seats are available on {flight_number} ({date})."

    sample = ", ".join(seats[:10])
    more = f" (and {len(seats) - 10} more)" if len(seats) > 10 else ""
    return f"{len(seats)} seats available on {flight_number} ({date}): {sample}{more}"


class MoveBookingInput(BaseModel):
    confirmation_code: str = Field(description="The booking confirmation code")
    new_flight_number: str = Field(description="The flight number to move to, e.g. AI205")
    new_date: str = Field(description="The new flight's date, e.g. 2026-08-14")
    new_seat: str = Field(description="The chosen seat on the new flight, e.g. 5A")


@tool(args_schema=MoveBookingInput)
def move_booking(
    confirmation_code: str,
    new_flight_number: str,
    new_date: str,
    new_seat: str,
    user_id: Annotated[str, InjectedState("user_id")],
) -> str:
    """Move a booking to a different flight and seat, freeing its old seat.

    Only call this after the user has confirmed a specific flight (from
    find_alternative_flights) and seat (from list_available_seats).
    """
    db = SessionLocal()
    try:
        booking, new_flight = booking_service.move_booking(
            db, uuid.UUID(user_id), confirmation_code, new_flight_number, new_date, new_seat
        )
    except BookingError as e:
        return str(e)
    finally:
        db.close()

    return (
        f"Booking {booking.confirmation_code} has been moved to {new_flight.flight_number} "
        f"on {new_flight.date} at {new_flight.departure_time}, seat {booking.seat}."
    )


class SelectSeatInput(BaseModel):
    confirmation_code: str = Field(description="The booking confirmation code")
    seat: str = Field(description="The desired seat, e.g. 14C")


@tool(args_schema=SelectSeatInput)
def select_seat(
    confirmation_code: str,
    seat: str,
    user_id: Annotated[str, InjectedState("user_id")],
) -> str:
    """Change the assigned seat on an existing booking, on its current flight (no date change)."""
    db = SessionLocal()
    try:
        booking, _ = booking_service.update_seat(db, uuid.UUID(user_id), confirmation_code, seat)
    except BookingError as e:
        return str(e)
    finally:
        db.close()

    return f"Seat for booking {booking.confirmation_code} has been changed to {booking.seat}."
