"""Billing service: DB-backed payment lookups, invoices and refund requests
for the billing agent's tools."""

import secrets
import string
import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Payment, Refund


class BillingError(Exception):
    """A user-facing error from a billing operation (not found, not eligible, etc.)."""


# Refunds that block a new request for the same payment. A "rejected"
# refund doesn't: the customer may ask again (e.g. with a better reason).
_ACTIVE_REFUND_STATUSES = ("requested", "processing", "completed")


def _generate_refund_number(db: Session) -> str:
    """A unique customer-facing refund reference, e.g. 'RF4F7K2X' — prefixed
    so it's visually distinguishable from confirmation codes and claim numbers."""
    alphabet = string.ascii_uppercase + string.digits
    for _ in range(5):
        code = "RF" + "".join(secrets.choice(alphabet) for _ in range(6))
        if db.query(Refund).filter(Refund.refund_number == code).first() is None:
            return code
    raise RuntimeError("Failed to generate a unique refund number after 5 attempts.")


def _get_owned_payment(db: Session, user_id: uuid.UUID, confirmation_code: str) -> Payment:
    """The most recent payment for a confirmation code, scoped to the user.
    Works for cancelled bookings too, since payments outlive them. Raises
    BillingError if there's no match — whether the code doesn't exist or
    belongs to someone else. Callers must not distinguish the two cases."""
    payment = (
        db.query(Payment)
        .filter(
            Payment.confirmation_code == confirmation_code.strip().upper(),
            Payment.user_id == user_id,
        )
        .order_by(Payment.created_at.desc())
        .first()
    )
    if payment is None:
        raise BillingError(f"No payment found for booking {confirmation_code!r}.")
    return payment


def _active_refund(db: Session, payment_id: uuid.UUID) -> Refund | None:
    return (
        db.query(Refund)
        .filter(Refund.payment_id == payment_id, Refund.status.in_(_ACTIVE_REFUND_STATUSES))
        .order_by(Refund.created_at.desc())
        .first()
    )


def list_payments_for_user(db: Session, user_id: uuid.UUID) -> list[tuple[Payment, Refund | None]]:
    """Every payment on the user's account, newest first, each with its
    active refund if there is one."""
    payments = (
        db.query(Payment).filter(Payment.user_id == user_id).order_by(Payment.created_at.desc()).all()
    )
    return [(payment, _active_refund(db, payment.id)) for payment in payments]


def get_invoice(db: Session, user_id: uuid.UUID, confirmation_code: str) -> tuple[Payment, Refund | None]:
    """The itemized payment for one booking, plus its active refund if any."""
    payment = _get_owned_payment(db, user_id, confirmation_code)
    return payment, _active_refund(db, payment.id)


def request_refund(
    db: Session, user_id: uuid.UUID, confirmation_code: str, reason: str
) -> tuple[Refund, Payment, bool]:
    """Request a refund for a cancelled booking's payment, or return the
    existing active refund if one was already requested.

    Refundable tickets go back to the original payment method; non-refundable
    ones become travel credit (per the Refunds FAQ). The booking must be
    cancelled first — an active booking is still a valid ticket.

    Returns (refund, payment, was_existing) so the tool layer can phrase the
    response differently for a fresh vs. deduplicated request.
    """
    reason = reason.strip()
    if not reason:
        raise BillingError("A reason for the refund is required.")

    payment = _get_owned_payment(db, user_id, confirmation_code)
    if not payment.booking_cancelled:
        raise BillingError(
            f"Booking {payment.confirmation_code} is still active, so it can't be refunded yet. "
            f"It has to be cancelled first — the user can ask to cancel it, then request the refund."
        )

    existing = _active_refund(db, payment.id)
    if existing is not None:
        return existing, payment, True

    refund = Refund(
        refund_number=_generate_refund_number(db),
        payment_id=payment.id,
        user_id=user_id,
        amount=payment.total,
        refund_to="original_payment" if payment.is_refundable else "travel_credit",
        status="requested",
        reason=reason,
    )
    db.add(refund)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise BillingError("Couldn't submit this refund request due to a database error. Please try again.")
    # expire_on_commit expired both objects; refresh before the tool layer
    # reads them after closing the session (see baggage_service).
    db.refresh(refund)
    db.refresh(payment)
    return refund, payment, False


def check_refund_status(db: Session, user_id: uuid.UUID, refund_number: str) -> tuple[Refund, Payment]:
    """A single refund's details plus the payment it's for. Raises
    BillingError if there's no match — whether the number doesn't exist or
    belongs to someone else."""
    row = (
        db.query(Refund, Payment)
        .join(Payment, Refund.payment_id == Payment.id)
        .filter(Refund.refund_number == refund_number.strip().upper(), Refund.user_id == user_id)
        .first()
    )
    if row is None:
        raise BillingError(f"No refund found for refund number {refund_number!r}.")
    return row
