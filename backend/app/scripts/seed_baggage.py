"""One-off dev seed script: attaches checked bags and baggage claims to the
existing demo bookings created by seed_bookings.py.

Usage (from backend/, with venv active, migrations applied via
`alembic upgrade head`, and seed_bookings.py already run):

    python -m app.scripts.seed_baggage

Safe to re-run; existing tag numbers and claim numbers are skipped/reused.
Depends on seed_bookings.py having already created ABC123/DEF456/DEL789
(demo1@example.com) and XYZ789/GHI321 (demo2@example.com) — if a
confirmation code isn't found, its bags/claims are skipped with a warning
rather than failing the whole run.
"""

from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

load_dotenv()  # must run before app.db.session is imported, since it reads DATABASE_URL at import time

from app.db.session import SessionLocal
from app.models import BaggageClaim, Booking, CheckedBag

# Each bag attaches to one of the 5 real seed_bookings.py confirmation
# codes. Statuses deliberately cover all six CheckedBag.status values.
SEED_BAGS = [
    {"confirmation_code": "ABC123", "tag_number": "1000000001", "status": "arrived", "weight_kg": 18.5},
    {"confirmation_code": "ABC123", "tag_number": "1000000002", "status": "arrived", "weight_kg": 22.0},
    {"confirmation_code": "DEF456", "tag_number": "1000000003", "status": "delayed", "weight_kg": 20.0},
    {"confirmation_code": "DEL789", "tag_number": "1000000004", "status": "lost", "weight_kg": 15.0},
    {"confirmation_code": "XYZ789", "tag_number": "1000000005", "status": "damaged", "weight_kg": 25.0},
    {"confirmation_code": "GHI321", "tag_number": "1000000006", "status": "arrived", "weight_kg": 19.0},
    {"confirmation_code": "GHI321", "tag_number": "1000000007", "status": "checked_in", "weight_kg": 12.0},
    {"confirmation_code": "GHI321", "tag_number": "1000000008", "status": "in_transit", "weight_kg": 16.5},
]

# Each claim attaches to one of the bags above by tag_number. Covers all
# three BaggageClaim.status values, including a resolved one with
# compensation set, so check_claim_status/track_bag have realistic variety.
SEED_CLAIMS = [
    {
        "claim_number": "BGDELAY1",
        "tag_number": "1000000003",
        "claim_type": "delayed",
        "description": "Bag did not arrive on the carousel; airline says it's on a later flight.",
        "status": "open",
        "compensation_amount": None,
        "resolved": False,
    },
    {
        "claim_number": "BGLOST01",
        "tag_number": "1000000004",
        "claim_type": "lost",
        "description": "Bag never arrived; ground staff filed a property irregularity report.",
        "status": "investigating",
        "compensation_amount": None,
        "resolved": False,
    },
    {
        "claim_number": "BGDAMAG1",
        "tag_number": "1000000005",
        "claim_type": "damaged",
        "description": "Wheel snapped off during handling.",
        "status": "resolved",
        "compensation_amount": 75.00,
        "resolved": True,
    },
]


def main() -> None:
    db = SessionLocal()
    try:
        bookings_by_code = {
            code: db.query(Booking).filter(Booking.confirmation_code == code).first()
            for code in {b["confirmation_code"] for b in SEED_BAGS}
        }

        bags_by_tag: dict[str, CheckedBag] = {}
        for b in SEED_BAGS:
            booking = bookings_by_code.get(b["confirmation_code"])
            if booking is None:
                print(f"Booking {b['confirmation_code']} not found — run seed_bookings.py first. Skipping.")
                continue

            existing = db.query(CheckedBag).filter(CheckedBag.tag_number == b["tag_number"]).first()
            if existing is not None:
                print(f"Bag {b['tag_number']} already exists, skipping.")
                bags_by_tag[b["tag_number"]] = existing
                continue

            bag = CheckedBag(
                booking_id=booking.id,
                tag_number=b["tag_number"],
                status=b["status"],
                weight_kg=b["weight_kg"],
            )
            db.add(bag)
            db.flush()
            bags_by_tag[b["tag_number"]] = bag
            print(f"Created bag {b['tag_number']} ({b['status']}) for booking {b['confirmation_code']}.")

        for c in SEED_CLAIMS:
            existing = db.query(BaggageClaim).filter(BaggageClaim.claim_number == c["claim_number"]).first()
            if existing is not None:
                print(f"Claim {c['claim_number']} already exists, skipping.")
                continue

            bag = bags_by_tag.get(c["tag_number"])
            if bag is None:
                print(f"Bag {c['tag_number']} not found for claim {c['claim_number']}, skipping.")
                continue

            booking = db.get(Booking, bag.booking_id)
            resolved_at = datetime.now(timezone.utc) - timedelta(days=1) if c["resolved"] else None

            db.add(BaggageClaim(
                claim_number=c["claim_number"],
                checked_bag_id=bag.id,
                user_id=booking.user_id,
                claim_type=c["claim_type"],
                description=c["description"],
                status=c["status"],
                compensation_amount=c["compensation_amount"],
                resolved_at=resolved_at,
            ))
            print(f"Created claim {c['claim_number']} ({c['claim_type']}, {c['status']}) for bag {c['tag_number']}.")

        db.commit()
        print("Done.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
