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

    Call this first when the user wants to change their flight date. Each option comes
    with a token — pass that exact token (not the flight number) to list_available_seats
    and move_booking; those tools reject anything that isn't a token from this call.
    """
    db = SessionLocal()
    try:
        booking, current_flight, options = booking_service.list_alternative_flights(
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
    if not options:
        return f"{header} No other flights are available on this route."

    lines = "\n".join(
        f"- [{token}] {f.flight_number} on {f.date} at {f.departure_time}" for token, f in options
    )
    return f"{header}\n\nOther available flights on this route:\n{lines}"


class SearchFlightsInput(BaseModel):
    origin: str = Field(description="Origin airport code, e.g. DEL")
    destination: str = Field(description="Destination airport code, e.g. BOM")
    date: str = Field(description="Travel date in YYYY-MM-DD format, e.g. 2026-08-14")


@tool(args_schema=SearchFlightsInput)
def search_flights(
    origin: str,
    destination: str,
    date: str,
    user_id: Annotated[str, InjectedState("user_id")],
) -> str:
    """Search for flights on a route and date to book a brand-new reservation.

    Call this first when the user wants to book a new flight (not change an
    existing booking — use find_alternative_flights for that). Each result
    comes with a token — pass that exact token (not the flight number) to
    list_available_seats and create_booking.
    """
    db = SessionLocal()
    try:
        options = booking_service.search_flights(db, uuid.UUID(user_id), origin, destination, date)
    finally:
        db.close()

    if not options:
        return f"No flights found from {origin.strip().upper()} to {destination.strip().upper()} on {date.strip()}."

    lines = "\n".join(
        f"- [{token}] {f.flight_number} on {f.date} at {f.departure_time}" for token, f in options
    )
    return f"Flights from {origin.strip().upper()} to {destination.strip().upper()} on {date.strip()}:\n{lines}"


class ListSeatsInput(BaseModel):
    flight_option_token: str = Field(
        description="The token shown next to the chosen flight from find_alternative_flights, e.g. 'opt_a1b2c3d4'"
    )


@tool(args_schema=ListSeatsInput)
def list_available_seats(
    flight_option_token: str,
    user_id: Annotated[str, InjectedState("user_id")],
) -> str:
    """List available seats on a flight the user picked from find_alternative_flights or search_flights.

    Takes the option token from either of those calls, not a flight number —
    call one of them first if you don't have one.
    """
    db = SessionLocal()
    try:
        flight, seats = booking_service.list_available_seats_for_token(
            db, uuid.UUID(user_id), flight_option_token
        )
    except BookingError as e:
        return str(e)
    finally:
        db.close()

    if not seats:
        return f"No seats are available on {flight.flight_number} ({flight.date})."

    sample = ", ".join(seats[:10])
    more = f" (and {len(seats) - 10} more)" if len(seats) > 10 else ""
    return f"{len(seats)} seats available on {flight.flight_number} ({flight.date}): {sample}{more}"


class MoveBookingInput(BaseModel):
    confirmation_code: str = Field(description="The booking confirmation code")
    flight_option_token: str = Field(
        description="The token from find_alternative_flights for the chosen flight, e.g. 'opt_a1b2c3d4'"
    )
    new_seat: str = Field(description="The chosen seat on the new flight, e.g. 5A")


@tool(args_schema=MoveBookingInput)
def move_booking(
    confirmation_code: str,
    flight_option_token: str,
    new_seat: str,
    user_id: Annotated[str, InjectedState("user_id")],
) -> str:
    """Move a booking to a different flight and seat, freeing its old seat.

    Only call this with a flight_option_token from find_alternative_flights
    and a seat the user picked from list_available_seats.
    """
    db = SessionLocal()
    try:
        booking, new_flight = booking_service.move_booking(
            db, uuid.UUID(user_id), confirmation_code, flight_option_token, new_seat
        )
    except BookingError as e:
        return str(e)
    finally:
        db.close()

    return (
        f"Booking {booking.confirmation_code} has been moved to {new_flight.flight_number} "
        f"on {new_flight.date} at {new_flight.departure_time}, seat {booking.seat}."
    )


class CreateBookingInput(BaseModel):
    flight_option_token: str = Field(
        description="The token from search_flights for the chosen flight, e.g. 'opt_a1b2c3d4'"
    )
    seat: str = Field(description="The chosen seat, e.g. 14C")
    passenger_name: str = Field(description="Full name of the passenger for this booking")


@tool(args_schema=CreateBookingInput)
def create_booking(
    flight_option_token: str,
    seat: str,
    passenger_name: str,
    user_id: Annotated[str, InjectedState("user_id")],
) -> str:
    """Create a brand-new booking on a flight the user picked from search_flights.

    Only call this with a flight_option_token from search_flights and a seat
    the user picked from list_available_seats.
    """
    db = SessionLocal()
    try:
        booking, flight = booking_service.create_booking(
            db, uuid.UUID(user_id), flight_option_token, seat, passenger_name
        )
    except BookingError as e:
        return str(e)
    finally:
        db.close()

    return (
        f"Booking confirmed! Confirmation code {booking.confirmation_code}: "
        f"{booking.passenger_name} on {flight.flight_number} from {flight.origin} "
        f"to {flight.destination} on {flight.date} at {flight.departure_time}, seat {booking.seat}."
    )


@tool(args_schema=ConfirmationCodeInput)
def cancel_booking(
    confirmation_code: str,
    user_id: Annotated[str, InjectedState("user_id")],
) -> str:
    """Cancel an existing booking, freeing its seat. This cannot be undone —
    make sure the user actually wants to cancel before calling this."""
    db = SessionLocal()
    try:
        code, flight = booking_service.cancel_booking_by_confirmation_code(
            db, uuid.UUID(user_id), confirmation_code
        )
    except BookingError as e:
        return str(e)
    finally:
        db.close()

    return (
        f"Booking {code} on {flight.flight_number} from {flight.origin} to "
        f"{flight.destination} on {flight.date} has been cancelled."
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