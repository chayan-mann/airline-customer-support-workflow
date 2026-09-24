"""One-off dev seed script: attaches payments (and a few refunds) to the demo
bookings created by seed_bookings.py, plus payments for a few bookings that
were already cancelled, so the refund flow has something to work with.

Usage (from backend/, with venv active, migrations applied via
`alembic upgrade head`, and seed_bookings.py already run):

    python -m app.scripts.seed_billing
    python -m app.scripts.seed_billing --user1 alice@example.com --user2 bob@example.com

Safe to re-run; existing payment references and refund numbers are skipped.
Active-booking payments need seed_bookings.py's ABC123/DEF456/DEL789
(user1) and XYZ789/GHI321 (user2) — a missing booking is skipped with a
warning rather than failing the whole run.
"""

import argparse
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

load_dotenv()  # must run before app.db.session is imported, since it reads DATABASE_URL at import time

from app.db.session import SessionLocal
from app.models import Booking, Flight, Payment, Refund, User

# Payments for bookings that still exist — description is built from the
# booking's flight at seed time.
ACTIVE_PAYMENTS = [
    {"reference": "PYABC123", "confirmation_code": "ABC123", "base_fare": 289.00, "taxes_fees": 41.35,
     "method": "Visa ending 4242", "is_refundable": True, "owner": 1},
    {"reference": "PYDEF456", "confirmation_code": "DEF456", "base_fare": 512.00, "taxes_fees": 88.20,
     "method": "Mastercard ending 5454", "is_refundable": False, "owner": 1},
    {"reference": "PYDEL789", "confirmation_code": "DEL789", "base_fare": 94.00, "taxes_fees": 17.60,
     "method": "PayPal", "is_refundable": True, "owner": 1},
    {"reference": "PYXYZ789", "confirmation_code": "XYZ789", "base_fare": 199.00, "taxes_fees": 32.10,
     "method": "American Express ending 1005", "is_refundable": False, "owner": 2},
    {"reference": "PYGHI321", "confirmation_code": "GHI321", "base_fare": 345.00, "taxes_fees": 52.75,
     "method": "Visa ending 1881", "is_refundable": True, "owner": 2},
]

# Payments whose booking was already cancelled (booking_id NULL, the same
# state cancel_booking leaves behind) — the confirmation codes don't exist
# in bookings. Covers: refund completed, refund processing, and two with no
# refund yet (one refundable -> original payment, one not -> travel credit).
CANCELLED_PAYMENTS = [
    {"reference": "PYCAN111", "confirmation_code": "CAN111", "description": "AA1234 JFK→LAX on 2026-07-20",
     "base_fare": 241.00, "taxes_fees": 36.90, "method": "Visa ending 4242", "is_refundable": True, "owner": 1},
    {"reference": "PYCAN222", "confirmation_code": "CAN222", "description": "AI101 DEL→BOM on 2026-07-28",
     "base_fare": 88.00, "taxes_fees": 16.40, "method": "Mastercard ending 5454", "is_refundable": False, "owner": 1},
    {"reference": "PYCAN444", "confirmation_code": "CAN444", "description": "BA100 LHR→JFK on 2026-07-30",
     "base_fare": 604.00, "taxes_fees": 121.50, "method": "Visa ending 4242", "is_refundable": True, "owner": 1},
    {"reference": "PYCAN333", "confirmation_code": "CAN333", "description": "UA789 SFO→ORD on 2026-07-25",
     "base_fare": 176.00, "taxes_fees": 28.45, "method": "Visa ending 1881", "is_refundable": True, "owner": 2},
]

SEED_REFUNDS = [
    {"refund_number": "RFDONE01", "payment_reference": "PYCAN111", "refund_to": "original_payment",
     "status": "completed", "reason": "Plans changed, cancelled the trip.", "completed": True},
    {"refund_number": "RFPROC01", "payment_reference": "PYCAN333", "refund_to": "original_payment",
     "status": "processing", "reason": "Conference was cancelled.", "completed": False},
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user1", default="demo1@example.com", help="Email of the first demo user")
    parser.add_argument("--user2", default="demo2@example.com", help="Email of the second demo user")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        users = {
            n: db.query(User).filter(User.email == email.strip().lower()).first()
            for n, email in ((1, args.user1), (2, args.user2))
        }

        payments_by_ref: dict[str, Payment] = {}

        def add_payment(p: dict, booking: Booking | None, description: str) -> None:
            existing = db.query(Payment).filter(Payment.reference == p["reference"]).first()
            if existing is not None:
                print(f"Payment {p['reference']} already exists, skipping.")
                payments_by_ref[p["reference"]] = existing
                return
            owner = users[p["owner"]]
            if owner is None:
                print(f"User {p['owner']} not found — run seed_bookings.py first. Skipping {p['reference']}.")
                return
            payment = Payment(
                reference=p["reference"],
                user_id=owner.id,
                booking_id=booking.id if booking else None,
                confirmation_code=p["confirmation_code"],
                description=description,
                base_fare=p["base_fare"],
                taxes_fees=p["taxes_fees"],
                method=p["method"],
                is_refundable=p["is_refundable"],
            )
            db.add(payment)
            db.flush()
            payments_by_ref[p["reference"]] = payment
            state = "active" if booking else "cancelled"
            print(f"Created payment {p['reference']} for {state} booking {p['confirmation_code']}.")

        for p in ACTIVE_PAYMENTS:
            row = (
                db.query(Booking, Flight)
                .join(Flight, Booking.flight_id == Flight.id)
                .filter(Booking.confirmation_code == p["confirmation_code"])
                .first()
            )
            if row is None:
                print(f"Booking {p['confirmation_code']} not found — run seed_bookings.py first. Skipping.")
                continue
            booking, flight = row
            add_payment(p, booking, f"{flight.flight_number} {flight.origin}→{flight.destination} on {flight.date}")

        for p in CANCELLED_PAYMENTS:
            add_payment(p, None, p["description"])

        for r in SEED_REFUNDS:
            if db.query(Refund).filter(Refund.refund_number == r["refund_number"]).first() is not None:
                print(f"Refund {r['refund_number']} already exists, skipping.")
                continue
            payment = payments_by_ref.get(r["payment_reference"])
            if payment is None:
                print(f"Payment {r['payment_reference']} not found for refund {r['refund_number']}, skipping.")
                continue
            db.add(Refund(
                refund_number=r["refund_number"],
                payment_id=payment.id,
                user_id=payment.user_id,
                amount=payment.total,
                refund_to=r["refund_to"],
                status=r["status"],
                reason=r["reason"],
                completed_at=datetime.now(timezone.utc) - timedelta(days=3) if r["completed"] else None,
            ))
            print(f"Created refund {r['refund_number']} ({r['status']}) for payment {r['payment_reference']}.")

        db.commit()
        print("Done.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
