"""Baggage action tools with structured (Pydantic) inputs."""

import uuid
from typing import Annotated

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState
from pydantic import BaseModel, Field

from app.db.session import SessionLocal
from app.service import baggage_service
from app.service.baggage_service import BaggageError


@tool
def list_my_baggage(user_id: Annotated[str, InjectedState("user_id")]) -> str:
    """List every checked bag across all of the current user's bookings."""
    db = SessionLocal()
    try:
        results = baggage_service.list_baggage_for_user(db, uuid.UUID(user_id))
    finally:
        db.close()

    if not results:
        return "You have no checked baggage on file."

    return "\n".join(
        f"Bag {bag.tag_number} ({bag.status}) on flight {flight.flight_number} "
        f"from {flight.origin} to {flight.destination} on {flight.date} "
        f"(booking {booking.confirmation_code})"
        + (f", {bag.weight_kg}kg" if bag.weight_kg is not None else "") + "."
        for bag, booking, flight in results
    )


class TagNumberInput(BaseModel):
    tag_number: str = Field(description="The 10-digit bag tag number, e.g. 1234567890")


@tool(args_schema=TagNumberInput)
def track_bag(tag_number: str, user_id: Annotated[str, InjectedState("user_id")]) -> str:
    """Look up a specific checked bag by its tag number, with full status and flight context.

    Use this when the user gives (or you already have) a bag tag number. Use
    list_my_baggage first if they don't know their tag number.
    """
    db = SessionLocal()
    try:
        bag, booking, flight = baggage_service.track_bag(db, uuid.UUID(user_id), tag_number)
    except BaggageError as e:
        return str(e)
    finally:
        db.close()

    weight = f", {bag.weight_kg}kg" if bag.weight_kg is not None else ""
    return (
        f"Bag {bag.tag_number}: status {bag.status}{weight}. Booking {booking.confirmation_code}, "
        f"flight {flight.flight_number} from {flight.origin} to {flight.destination} "
        f"on {flight.date} at {flight.departure_time}."
    )


class ReportBaggageIssueInput(BaseModel):
    tag_number: str = Field(description="The 10-digit bag tag number, e.g. 1234567890")
    claim_type: str = Field(description="One of: lost, delayed, damaged")
    description: str = Field(description="A description of the issue in the user's own words")


@tool(args_schema=ReportBaggageIssueInput)
def report_baggage_issue(
    tag_number: str,
    claim_type: str,
    description: str,
    user_id: Annotated[str, InjectedState("user_id")],
) -> str:
    """File a claim for a lost, delayed, or damaged bag.

    If the bag already has an open or in-progress claim, this returns that
    existing claim instead of filing a duplicate.
    """
    db = SessionLocal()
    try:
        claim, bag, was_existing = baggage_service.report_baggage_issue(
            db, uuid.UUID(user_id), tag_number, claim_type, description
        )
    except BaggageError as e:
        return str(e)
    finally:
        db.close()

    if was_existing:
        return (
            f"Bag {bag.tag_number} already has an active claim: {claim.claim_number} "
            f"({claim.claim_type}, status: {claim.status}). No new claim was filed."
        )
    return (
        f"Claim {claim.claim_number} filed for bag {bag.tag_number} ({claim.claim_type}). "
        f"Bag status updated to {bag.status}. We'll update you as it progresses."
    )


class ClaimNumberInput(BaseModel):
    claim_number: str = Field(description="The claim reference number, e.g. BG4F7K2X")


@tool(args_schema=ClaimNumberInput)
def check_claim_status(claim_number: str, user_id: Annotated[str, InjectedState("user_id")]) -> str:
    """Look up the status and details of a previously filed baggage claim."""
    db = SessionLocal()
    try:
        claim, bag, booking, flight = baggage_service.check_claim_status(
            db, uuid.UUID(user_id), claim_number
        )
    except BaggageError as e:
        return str(e)
    finally:
        db.close()

    compensation = (
        f" Compensation: ${claim.compensation_amount:.2f}." if claim.compensation_amount is not None else ""
    )
    return (
        f"Claim {claim.claim_number}: {claim.claim_type}, status {claim.status}.{compensation} "
        f"Bag {bag.tag_number} (booking {booking.confirmation_code}, flight {flight.flight_number} "
        f"from {flight.origin} to {flight.destination} on {flight.date}). {claim.description}"
    )
