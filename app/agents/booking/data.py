"""Mock in-memory reservations store for the booking agent (demo data only)."""

from copy import deepcopy

_BOOKINGS = {
    "ABC123": {
        "passenger_name": "Jordan Lee",
        "flight_number": "AA1234",
        "origin": "JFK",
        "destination": "LAX",
        "date": "2026-08-02",
        "seat": "14C",
        "status": "confirmed",
    },
    "XYZ789": {
        "passenger_name": "Sam Rivera",
        "flight_number": "DL456",
        "origin": "ORD",
        "destination": "MIA",
        "date": "2026-08-10",
        "seat": "22A",
        "status": "confirmed",
    },
}


def get_booking(confirmation_code: str) -> dict | None:
    booking = _BOOKINGS.get(confirmation_code.upper())
    return deepcopy(booking) if booking else None


def update_booking(confirmation_code: str, **fields) -> dict | None:
    code = confirmation_code.upper()
    booking = _BOOKINGS.get(code)
    if booking is None:
        return None
    booking.update(fields)
    return deepcopy(booking)
