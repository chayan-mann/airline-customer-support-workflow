"""One-off dev seed script: creates demo flights/bookings across two users.

Usage (from backend/, with venv active and migrations applied via
`alembic upgrade head`):

    python -m app.scripts.seed_bookings
    python -m app.scripts.seed_bookings --user1 alice@example.com --user2 bob@example.com

If a given user doesn't exist yet, it's created with a demo password (printed
to stdout) so this script is turnkey and doesn't require registering via the
API first. Safe to re-run; existing confirmation codes, flight numbers, and
users are all skipped/reused.
"""

import argparse

from dotenv import load_dotenv

load_dotenv()  # must run before app.db.session is imported, since it reads DATABASE_URL at import time

from app.db.session import SessionLocal
from app.models import Booking, Flight, User
from app.security import hash_password

DEMO_PASSWORD = "password123"

SEED_FLIGHTS = [
    {"flight_number": "AA1234", "origin": "JFK", "destination": "LAX", "date": "2026-08-02"},
    {"flight_number": "DL456", "origin": "ORD", "destination": "MIA", "date": "2026-08-10"},
    {"flight_number": "UA789", "origin": "SFO", "destination": "SEA", "date": "2026-08-15"},
    {"flight_number": "AA2001", "origin": "LAX", "destination": "JFK", "date": "2026-08-20"},
    {"flight_number": "BA100", "origin": "JFK", "destination": "LHR", "date": "2026-09-01"},
    {"flight_number": "DL789", "origin": "ATL", "destination": "ORD", "date": "2026-09-05"},
    {"flight_number": "UA202", "origin": "SEA", "destination": "DEN", "date": "2026-09-10"},
    {"flight_number": "AA303", "origin": "MIA", "destination": "JFK", "date": "2026-09-12"},
    {"flight_number": "WN505", "origin": "DEN", "destination": "LAS", "date": "2026-09-15"},
    {"flight_number": "DL900", "origin": "ORD", "destination": "SFO", "date": "2026-09-20"},
]

# Each entry's "owner" key picks which CLI user (1 or 2) the booking belongs to.
SEED_BOOKINGS = [
    {"confirmation_code": "ABC123", "passenger_name": "Jordan Lee", "seat": "14C",
     "status": "confirmed", "flight_number": "AA1234", "owner": 1},
    {"confirmation_code": "DEF456", "passenger_name": "Jordan Lee", "seat": "7A",
     "status": "confirmed", "flight_number": "BA100", "owner": 1},
    {"confirmation_code": "XYZ789", "passenger_name": "Sam Rivera", "seat": "22A",
     "status": "confirmed", "flight_number": "DL456", "owner": 2},
    {"confirmation_code": "GHI321", "passenger_name": "Sam Rivera", "seat": "3B",
     "status": "confirmed", "flight_number": "UA789", "owner": 2},
]


def _get_or_create_user(db, email: str) -> User:
    email = email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        user = User(email=email, password_hash=hash_password(DEMO_PASSWORD))
        db.add(user)
        db.flush()
        print(f"Created user {email} (password: {DEMO_PASSWORD!r})")
    else:
        print(f"Using existing user {email}")
    return user


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user1", default="demo1@example.com", help="Email for the first demo user")
    parser.add_argument("--user2", default="demo2@example.com", help="Email for the second demo user")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        users = {1: _get_or_create_user(db, args.user1), 2: _get_or_create_user(db, args.user2)}

        flights_by_number = {}
        for f in SEED_FLIGHTS:
            flight = db.query(Flight).filter(Flight.flight_number == f["flight_number"]).first()
            if flight is None:
                flight = Flight(**f)
                db.add(flight)
                db.flush()
            flights_by_number[f["flight_number"]] = flight
        print(f"Seeded {len(flights_by_number)} flights.")

        for b in SEED_BOOKINGS:
            existing = db.query(Booking).filter(
                Booking.confirmation_code == b["confirmation_code"]
            ).first()
            if existing is not None:
                print(f"Booking {b['confirmation_code']} already exists, skipping.")
                continue
            fields = dict(b)
            flight = flights_by_number[fields.pop("flight_number")]
            owner = users[fields.pop("owner")]
            db.add(Booking(user_id=owner.id, flight_id=flight.id, **fields))
            print(f"Created booking {b['confirmation_code']} for {owner.email}.")

        db.commit()
        print("Done.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
