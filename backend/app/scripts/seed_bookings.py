"""One-off dev seed script: creates demo flights, seat maps, and bookings
across two users.

Usage (from backend/, with venv active and migrations applied via
`alembic upgrade head`):

    python -m app.scripts.seed_bookings
    python -m app.scripts.seed_bookings --user1 alice@example.com --user2 bob@example.com

If a given user doesn't exist yet, it's created with a demo password (printed
to stdout) so this script is turnkey and doesn't require registering via the
API first. Safe to re-run; existing confirmation codes, flight numbers,
seats, and users are all skipped/reused.

A few routes (DEL<->BOM, JFK<->LAX) are seeded with several flights on
different dates/times so the "show me other available dates for my route"
flow has real alternatives to offer.
"""

import argparse

from dotenv import load_dotenv

load_dotenv()  # must run before app.db.session is imported, since it reads DATABASE_URL at import time

from app.db.session import SessionLocal
from app.models import Booking, Flight, Seat, User
from app.security import hash_password

DEMO_PASSWORD = "password123"

# Every flight gets the same seat map: rows 1-25, columns A-F (150 seats).
SEAT_ROWS = range(1, 26)
SEAT_COLUMNS = "ABCDEF"

SEED_FLIGHTS = [
    # DEL <-> BOM: several date/time options on the same route, so a date
    # change has real alternatives (matches the "Delhi to Bombay on 14th Aug"
    # example this was designed around).
    {"flight_number": "AI101", "origin": "DEL", "destination": "BOM", "date": "2026-08-14", "departure_time": "08:00"},
    {"flight_number": "AI205", "origin": "DEL", "destination": "BOM", "date": "2026-08-14", "departure_time": "14:30"},
    {"flight_number": "AI310", "origin": "DEL", "destination": "BOM", "date": "2026-08-15", "departure_time": "09:15"},
    {"flight_number": "AI415", "origin": "DEL", "destination": "BOM", "date": "2026-08-16", "departure_time": "18:45"},
    # JFK <-> LAX: another route with overlapping dates.
    {"flight_number": "AA1234", "origin": "JFK", "destination": "LAX", "date": "2026-08-02", "departure_time": "07:00"},
    {"flight_number": "AA1250", "origin": "JFK", "destination": "LAX", "date": "2026-08-05", "departure_time": "12:00"},
    {"flight_number": "AA1299", "origin": "JFK", "destination": "LAX", "date": "2026-08-09", "departure_time": "19:30"},
    # One-off flights on other routes, for variety.
    {"flight_number": "DL456", "origin": "ORD", "destination": "MIA", "date": "2026-08-10", "departure_time": "10:00"},
    {"flight_number": "UA789", "origin": "SFO", "destination": "SEA", "date": "2026-08-15", "departure_time": "06:45"},
    {"flight_number": "AA2001", "origin": "LAX", "destination": "JFK", "date": "2026-08-20", "departure_time": "15:00"},
    {"flight_number": "BA100", "origin": "JFK", "destination": "LHR", "date": "2026-09-01", "departure_time": "21:00"},
    {"flight_number": "DL789", "origin": "ATL", "destination": "ORD", "date": "2026-09-05", "departure_time": "11:20"},
    {"flight_number": "UA202", "origin": "SEA", "destination": "DEN", "date": "2026-09-10", "departure_time": "08:30"},
    {"flight_number": "AA303", "origin": "MIA", "destination": "JFK", "date": "2026-09-12", "departure_time": "13:10"},
    {"flight_number": "WN505", "origin": "DEN", "destination": "LAS", "date": "2026-09-15", "departure_time": "16:00"},
    {"flight_number": "DL900", "origin": "ORD", "destination": "SFO", "date": "2026-09-20", "departure_time": "09:45"},
]

# Each entry's "owner" key picks which CLI user (1 or 2) the booking belongs to.
# "flight_key" matches a (flight_number, date) pair in SEED_FLIGHTS, since a
# flight_number alone can now appear on multiple dates (e.g. AI101 only
# appears once, but the route has several sibling flight numbers).
SEED_BOOKINGS = [
    {"confirmation_code": "ABC123", "passenger_name": "Jordan Lee", "seat": "14C",
     "status": "confirmed", "flight_number": "AA1234", "flight_date": "2026-08-02", "owner": 1},
    {"confirmation_code": "DEF456", "passenger_name": "Jordan Lee", "seat": "7A",
     "status": "confirmed", "flight_number": "BA100", "flight_date": "2026-09-01", "owner": 1},
    {"confirmation_code": "DEL789", "passenger_name": "Jordan Lee", "seat": "5A",
     "status": "confirmed", "flight_number": "AI101", "flight_date": "2026-08-14", "owner": 1},
    {"confirmation_code": "XYZ789", "passenger_name": "Sam Rivera", "seat": "22A",
     "status": "confirmed", "flight_number": "DL456", "flight_date": "2026-08-10", "owner": 2},
    {"confirmation_code": "GHI321", "passenger_name": "Sam Rivera", "seat": "3B",
     "status": "confirmed", "flight_number": "UA789", "flight_date": "2026-08-15", "owner": 2},
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


def _get_or_create_flight(db, f: dict) -> Flight:
    flight = (
        db.query(Flight)
        .filter(Flight.flight_number == f["flight_number"], Flight.date == f["date"])
        .first()
    )
    if flight is not None:
        return flight

    flight = Flight(**f)
    db.add(flight)
    db.flush()

    seats = [
        Seat(flight_id=flight.id, seat_number=f"{row}{col}")
        for row in SEAT_ROWS
        for col in SEAT_COLUMNS
    ]
    db.bulk_save_objects(seats)
    return flight


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user1", default="demo1@example.com", help="Email for the first demo user")
    parser.add_argument("--user2", default="demo2@example.com", help="Email for the second demo user")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        users = {1: _get_or_create_user(db, args.user1), 2: _get_or_create_user(db, args.user2)}

        flights_by_key = {}
        for f in SEED_FLIGHTS:
            flight = _get_or_create_flight(db, f)
            flights_by_key[(f["flight_number"], f["date"])] = flight
        print(f"Seeded {len(flights_by_key)} flights (with a {len(SEAT_ROWS) * len(SEAT_COLUMNS)}-seat map each).")

        for b in SEED_BOOKINGS:
            existing = db.query(Booking).filter(
                Booking.confirmation_code == b["confirmation_code"]
            ).first()
            if existing is not None:
                print(f"Booking {b['confirmation_code']} already exists, skipping.")
                continue
            fields = dict(b)
            flight = flights_by_key[(fields.pop("flight_number"), fields.pop("flight_date"))]
            owner = users[fields.pop("owner")]
            db.add(Booking(user_id=owner.id, flight_id=flight.id, **fields))
            print(f"Created booking {b['confirmation_code']} for {owner.email}.")

        db.commit()
        print("Done.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
