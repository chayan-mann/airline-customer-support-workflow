"""Mock booking action tools with structured (Pydantic) inputs."""

from langchain_core.tools import tool
from pydantic import BaseModel, Field

import uuid
from typing import Annotated

from langgraph.prebuilt import InjectedState
from app.agentic_ai.agents.booking import data
from app.db.session import SessionLocal 
from app.service import booking_service

# this tool is calling real service function, so we can use the real database session and models
@tool
def list_my_bookings(user_id: Annotated[str, InjectedState("user_id")]) -> str:
    """Look up an existing booking by confirmation code."""
    db = SessionLocal()
    try:
        results = booking_service.list_bookings_for_user(db, uuid.UUID(user_id))
    finally:
        db.close()
    
    if not results:
        return "No bookings found for this user."

    return "\n".join(
        f"Booking {booking.confirmation_code}: {booking.passenger_name} on flight "
        f"{flight.flight_number} from {flight.origin} to {flight.destination} "
        f"on {flight.date}, seat {booking.seat}. Status: {booking.status}."
        for booking, flight in results
    )


class ChangeFlightDateInput(BaseModel):
    confirmation_code: str = Field(description="The booking confirmation code")
    new_date: str = Field(description="The new flight date, e.g. 2026-09-01")


@tool(args_schema=ChangeFlightDateInput)
def change_flight_date(confirmation_code: str, new_date: str) -> str:
    """Change the flight date on an existing booking."""
    booking = data.update_booking(confirmation_code, date=new_date)
    if booking is None:
        return f"No booking found for confirmation code {confirmation_code!r}."
    return f"Booking {confirmation_code.upper()} has been moved to {new_date}."


class SelectSeatInput(BaseModel):
    confirmation_code: str = Field(description="The booking confirmation code")
    seat: str = Field(description="The desired seat, e.g. 14C")


@tool(args_schema=SelectSeatInput)
def select_seat(confirmation_code: str, seat: str) -> str:
    """Change the assigned seat on an existing booking."""
    booking = data.update_booking(confirmation_code, seat=seat)
    if booking is None:
        return f"No booking found for confirmation code {confirmation_code!r}."
    return f"Seat for booking {confirmation_code.upper()} has been changed to {seat}."
