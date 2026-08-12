"""One-off dev seed script: creates demo flights/bookings for an existing user.

Usage (from backend/, with venv active and migrations applied via
`alembic upgrade head`):

    python -m app.scripts.seed_bookings someone@example.com

The user must already be registered (via POST /auth/register or the
frontend) — bookings require a real user_id to attach to. Safe to re-run;
existing confirmation codes and flight numbers are skipped.
"""

import argparse
import sys

from dotenv import load_dotenv

load_dotenv()  # must run before app.db.session is imported, since it reads DATABASE_URL at import time

from app.db.session import SessionLocal
from app.models import Booking, Flight, User

SEED_FLIGHTS = [
    {"flight_number": "AA1234", "origin": "JFK", "destination": "LAX", "date": "2026-08-02"},
    {"flight_number": "DL456", "origin": "ORD", "destination": "MIA", "date": "2026-08-10"},
]

SEED_BOOKINGS = [
    {
        "confirmation_code": "ABC123",
        "passenger_name": "Jordan Lee",
        "seat": "14C",
        "status": "confirmed",
        "flight_number": "AA1234",
    },
    {
        "confirmation_code": "XYZ789",
        "passenger_name": "Sam Rivera",
        "seat": "22A",
        "status": "confirmed",
        "flight_number": "DL456",
    },
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("email", help="Email of an already-registered user to own the seeded bookings")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == args.email.strip().lower()).first()
        if user is None:
            print(
                f"No user found with email {args.email!r}. Register this user first "
                f"(via POST /auth/register or the frontend) and re-run this script.",
                file=sys.stderr,
            )
            sys.exit(1)

        flights_by_number = {}
        for f in SEED_FLIGHTS:
            flight = db.query(Flight).filter(Flight.flight_number == f["flight_number"]).first()
            if flight is None:
                flight = Flight(**f)
                db.add(flight)
                db.flush()
            flights_by_number[f["flight_number"]] = flight

        for b in SEED_BOOKINGS:
            existing = db.query(Booking).filter(
                Booking.confirmation_code == b["confirmation_code"]
            ).first()
            if existing is not None:
                print(f"Booking {b['confirmation_code']} already exists, skipping.")
                continue
            fields = dict(b)
            flight = flights_by_number[fields.pop("flight_number")]
            db.add(Booking(user_id=user.id, flight_id=flight.id, **fields))

        db.commit()
        print(f"Seeded bookings for user {user.email}.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
