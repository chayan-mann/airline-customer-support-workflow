"""Baggage service: DB-backed lookups and claim filing for the baggage
agent's tools."""

import secrets
import string
import uuid
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import BaggageClaim, Booking, CheckedBag, Flight


class BaggageError(Exception):
    """A user-facing error from a baggage operation (not found, invalid claim type, etc.)."""


VALID_CLAIM_TYPES = ("lost", "delayed", "damaged")

# Claims considered "active" for report_baggage_issue's dedup check. A bag
# already under an unresolved claim shouldn't get a second one filed
# against it — this intentionally includes "investigating", not just
# "open", since a claim already being worked is exactly the case a
# re-report should collapse into, not duplicate. A "resolved" claim does
# NOT block a new report (e.g. a bag lost on one trip, damaged on a later
# one is a genuinely new issue).
_ACTIVE_CLAIM_STATUSES = ("open", "investigating")


def _generate_claim_number(db: Session) -> str:
    """A unique customer-facing claim reference, e.g. 'BG4F7K2X' — prefixed
    so it's visually distinguishable from a booking confirmation_code."""
    alphabet = string.ascii_uppercase + string.digits
    for _ in range(5):
        code = "BG" + "".join(secrets.choice(alphabet) for _ in range(6))
        if db.query(BaggageClaim).filter(BaggageClaim.claim_number == code).first() is None:
            return code
    raise RuntimeError("Failed to generate a unique claim number after 5 attempts.")


def _get_owned_bag(db: Session, user_id: uuid.UUID, tag_number: str) -> tuple[CheckedBag, Booking, Flight]:
    """Look up a checked bag by tag number, scoped to the given user via its
    booking. Raises BaggageError if there's no match — whether the tag
    doesn't exist or belongs to someone else's booking. Callers must not
    distinguish the two cases in any user-facing message."""
    row = (
        db.query(CheckedBag, Booking, Flight)
        .join(Booking, CheckedBag.booking_id == Booking.id)
        .join(Flight, Booking.flight_id == Flight.id)
        .filter(CheckedBag.tag_number == tag_number.strip(), Booking.user_id == user_id)
        .first()
    )
    if row is None:
        raise BaggageError(f"No bag found for tag number {tag_number!r}.")
    return row


def _get_owned_claim(
    db: Session, user_id: uuid.UUID, claim_number: str
) -> tuple[BaggageClaim, CheckedBag, Booking, Flight]:
    """Look up a claim by claim number, scoped to the given user. Raises
    BaggageError if there's no match — whether the claim number doesn't
    exist or belongs to someone else. Callers must not distinguish the two
    cases in any user-facing message."""
    row = (
        db.query(BaggageClaim, CheckedBag, Booking, Flight)
        .join(CheckedBag, BaggageClaim.checked_bag_id == CheckedBag.id)
        .join(Booking, CheckedBag.booking_id == Booking.id)
        .join(Flight, Booking.flight_id == Flight.id)
        .filter(BaggageClaim.claim_number == claim_number.strip().upper(), BaggageClaim.user_id == user_id)
        .first()
    )
    if row is None:
        raise BaggageError(f"No claim found for claim number {claim_number!r}.")
    return row


def list_baggage_for_user(db: Session, user_id: uuid.UUID) -> list[tuple[CheckedBag, Booking, Flight]]:
    """Every checked bag across all of the user's bookings, most recent flight first."""
    return (
        db.query(CheckedBag, Booking, Flight)
        .join(Booking, CheckedBag.booking_id == Booking.id)
        .join(Flight, Booking.flight_id == Flight.id)
        .filter(Booking.user_id == user_id)
        .order_by(Flight.date.desc())
        .all()
    )


def track_bag(db: Session, user_id: uuid.UUID, tag_number: str) -> tuple[CheckedBag, Booking, Flight]:
    """A single bag's full status plus its booking/flight context."""
    return _get_owned_bag(db, user_id, tag_number)


def report_baggage_issue(
    db: Session, user_id: uuid.UUID, tag_number: str, claim_type: str, description: str
) -> tuple[BaggageClaim, CheckedBag, bool]:
    """File a new claim against a bag, or return the existing one if it
    already has an active (open/investigating) claim — avoids filing a
    duplicate claim for the same underlying issue.

    Returns (claim, bag, was_existing) so the tool layer can phrase the
    response differently for a fresh vs. deduplicated claim.
    """
    claim_type = claim_type.strip().lower()
    if claim_type not in VALID_CLAIM_TYPES:
        raise BaggageError(
            f"{claim_type!r} isn't a valid claim type. Must be one of: {', '.join(VALID_CLAIM_TYPES)}."
        )

    description = description.strip()
    if not description:
        raise BaggageError("A description of the issue is required to file a claim.")

    bag, _booking, _flight = _get_owned_bag(db, user_id, tag_number)

    existing = (
        db.query(BaggageClaim)
        .filter(
            BaggageClaim.checked_bag_id == bag.id,
            BaggageClaim.status.in_(_ACTIVE_CLAIM_STATUSES),
        )
        .first()
    )
    if existing is not None:
        # No commit happened on this path — existing and bag both came from
        # queries in this same still-open session, so no refresh is needed.
        return existing, bag, True

    claim = BaggageClaim(
        claim_number=_generate_claim_number(db),
        checked_bag_id=bag.id,
        user_id=user_id,
        claim_type=claim_type,
        description=description,
        status="open",
    )
    db.add(claim)
    bag.status = claim_type
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise BaggageError("Couldn't file this claim due to a database error. Please try again.")
    # expire_on_commit (the sessionmaker default) expired both claim and bag
    # — this project's recurring footgun (see move_booking/
    # list_alternative_flights/search_flights in booking_service.py) — so
    # both need refreshing before the tool layer reads their attributes
    # after closing the session.
    db.refresh(claim)
    db.refresh(bag)
    return claim, bag, False


def check_claim_status(
    db: Session, user_id: uuid.UUID, claim_number: str
) -> tuple[BaggageClaim, CheckedBag, Booking, Flight]:
    """A single claim's full details plus its bag/booking/flight context."""
    return _get_owned_claim(db, user_id, claim_number)
