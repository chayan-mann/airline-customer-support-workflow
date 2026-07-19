"""Mock booking action tools with structured (Pydantic) inputs."""

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.agents.booking import data


class LookupBookingInput(BaseModel):
    confirmation_code: str = Field(description="The booking confirmation code, e.g. ABC123")


@tool(args_schema=LookupBookingInput)
def lookup_booking(confirmation_code: str) -> str:
    """Look up an existing booking by confirmation code."""
    booking = data.get_booking(confirmation_code)
    if booking is None:
        return f"No booking found for confirmation code {confirmation_code!r}."
    return (
        f"Booking {confirmation_code.upper()}: {booking['passenger_name']} on flight "
        f"{booking['flight_number']} from {booking['origin']} to {booking['destination']} "
        f"on {booking['date']}, seat {booking['seat']}. Status: {booking['status']}."
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
