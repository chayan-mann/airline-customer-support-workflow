"""Billing action tools with structured (Pydantic) inputs."""

import uuid
from typing import Annotated

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState
from pydantic import BaseModel, Field

from app.db.session import SessionLocal
from app.models import Payment, Refund
from app.service import billing_service
from app.service.billing_service import BillingError

_REFUND_DESTINATIONS = {
    "original_payment": "to the original payment method (usually 7-10 business days)",
    "travel_credit": "as travel credit (non-refundable ticket)",
}


def _money(payment: Payment, amount: float) -> str:
    return f"{payment.currency} {amount:.2f}"


def _refund_summary(refund: Refund, payment: Payment) -> str:
    return (
        f"Refund {refund.refund_number}: {_money(payment, refund.amount)} "
        f"{_REFUND_DESTINATIONS.get(refund.refund_to, refund.refund_to)}, status {refund.status}"
    )


@tool
def list_my_payments(user_id: Annotated[str, InjectedState("user_id")]) -> str:
    """List every payment on the current user's account, including for
    cancelled bookings, with any refund in progress."""
    db = SessionLocal()
    try:
        results = billing_service.list_payments_for_user(db, uuid.UUID(user_id))
    finally:
        db.close()

    if not results:
        return "You have no payments on file."

    lines = []
    for payment, refund in results:
        booking_state = "booking cancelled" if payment.booking_cancelled else "booking active"
        refund_note = f"; {_refund_summary(refund, payment)}" if refund else ""
        lines.append(
            f"Payment {payment.reference} for booking {payment.confirmation_code} ({payment.description}): "
            f"{_money(payment, payment.total)} on {payment.method}, "
            f"{'refundable' if payment.is_refundable else 'non-refundable'} fare, {booking_state}{refund_note}."
        )
    return "\n".join(lines)


class ConfirmationCodeInput(BaseModel):
    confirmation_code: str = Field(description="The booking confirmation code, e.g. ABC123")


@tool(args_schema=ConfirmationCodeInput)
def get_invoice(confirmation_code: str, user_id: Annotated[str, InjectedState("user_id")]) -> str:
    """Get the itemized invoice (fare, taxes and fees, total, payment method)
    for one booking. Works for cancelled bookings too."""
    db = SessionLocal()
    try:
        payment, refund = billing_service.get_invoice(db, uuid.UUID(user_id), confirmation_code)
    except BillingError as e:
        return str(e)
    finally:
        db.close()

    refund_note = f"\n{_refund_summary(refund, payment)}." if refund else ""
    return (
        f"Invoice for booking {payment.confirmation_code} — {payment.description}\n"
        f"Payment reference: {payment.reference}, paid {payment.created_at:%Y-%m-%d} with {payment.method}\n"
        f"Base fare: {_money(payment, payment.base_fare)}\n"
        f"Taxes & fees: {_money(payment, payment.taxes_fees)}\n"
        f"Total: {_money(payment, payment.total)}\n"
        f"Fare type: {'refundable' if payment.is_refundable else 'non-refundable'}"
        f"{refund_note}"
    )


class RequestRefundInput(BaseModel):
    confirmation_code: str = Field(description="The confirmation code of the cancelled booking, e.g. ABC123")
    reason: str = Field(description="Why the user wants a refund, in their own words")


@tool(args_schema=RequestRefundInput)
def request_refund(
    confirmation_code: str,
    reason: str,
    user_id: Annotated[str, InjectedState("user_id")],
) -> str:
    """Request a refund for a cancelled booking. Refundable fares go back to
    the original payment method; non-refundable fares become travel credit.

    The booking must already be cancelled. If a refund was already requested
    for it, this returns that existing refund instead of creating another.
    """
    db = SessionLocal()
    try:
        refund, payment, was_existing = billing_service.request_refund(
            db, uuid.UUID(user_id), confirmation_code, reason
        )
    except BillingError as e:
        return str(e)
    finally:
        db.close()

    if was_existing:
        return (
            f"Booking {payment.confirmation_code} already has a refund on file — "
            f"{_refund_summary(refund, payment)}. No new request was made."
        )
    return f"Refund requested for booking {payment.confirmation_code}. {_refund_summary(refund, payment)}."


class RefundNumberInput(BaseModel):
    refund_number: str = Field(description="The refund reference number, e.g. RF4F7K2X")


@tool(args_schema=RefundNumberInput)
def check_refund_status(refund_number: str, user_id: Annotated[str, InjectedState("user_id")]) -> str:
    """Look up the status of a previously requested refund by its refund number."""
    db = SessionLocal()
    try:
        refund, payment = billing_service.check_refund_status(db, uuid.UUID(user_id), refund_number)
    except BillingError as e:
        return str(e)
    finally:
        db.close()

    completed = f", completed {refund.completed_at:%Y-%m-%d}" if refund.completed_at else ""
    return (
        f"{_refund_summary(refund, payment)}{completed}. "
        f"For booking {payment.confirmation_code} ({payment.description}), requested {refund.created_at:%Y-%m-%d}. "
        f"Reason given: {refund.reason}"
    )
