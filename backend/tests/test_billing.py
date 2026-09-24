"""Billing service rules and tools, against a throwaway in-memory SQLite
database built from the models (tests only — the app's real schema is
managed by Alembic)."""

import uuid

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.agentic_ai.agents.billing import tools as billing_tools
from app.db.session import Base
from app.models import Booking, Flight, Payment, Refund, User
from app.service import billing_service
from app.service.billing_service import BillingError


@pytest.fixture
def Session(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    # SQLite ignores foreign keys unless asked; payments rely on SET NULL.
    @event.listens_for(engine, "connect")
    def _fks_on(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(billing_tools, "SessionLocal", session_factory)
    return session_factory


@pytest.fixture
def db(Session):
    session = Session()
    yield session
    session.close()


def _user(db, email):
    user = User(email=email, password_hash="x")
    db.add(user)
    db.flush()
    return user


def _booking(db, user, code="ABC123"):
    flight = Flight(flight_number="AI101", origin="DEL", destination="BOM", date="2026-10-01", departure_time="07:00")
    db.add(flight)
    db.flush()
    booking = Booking(
        confirmation_code=code, passenger_name="Jordan Lee", seat="14C",
        status="confirmed", user_id=user.id, flight_id=flight.id,
    )
    db.add(booking)
    db.flush()
    return booking


def _payment(db, user, booking=None, code="ABC123", refundable=True, reference="PY000001"):
    payment = Payment(
        reference=reference, user_id=user.id, booking_id=booking.id if booking else None,
        confirmation_code=code, description="AI101 DEL→BOM on 2026-10-01",
        base_fare=200.0, taxes_fees=35.5, method="Visa ending 4242", is_refundable=refundable,
    )
    db.add(payment)
    db.commit()
    return payment


@pytest.fixture
def alice(db):
    return _user(db, "alice@example.com")


@pytest.fixture
def bob(db):
    return _user(db, "bob@example.com")


def test_payment_survives_booking_cancellation(db, alice):
    booking = _booking(db, alice)
    payment = _payment(db, alice, booking)
    assert not payment.booking_cancelled

    db.delete(booking)  # what cancel_booking does
    db.commit()
    db.refresh(payment)

    assert payment.booking_id is None
    assert payment.booking_cancelled


def test_refund_blocked_while_booking_is_active(db, alice):
    _payment(db, alice, _booking(db, alice))

    with pytest.raises(BillingError, match="still active"):
        billing_service.request_refund(db, alice.id, "ABC123", "changed plans")
    assert db.query(Refund).count() == 0


def test_refundable_fare_refunds_to_original_payment(db, alice):
    _payment(db, alice, code="CAN111", refundable=True)

    refund, payment, was_existing = billing_service.request_refund(db, alice.id, "can111", "changed plans")

    assert not was_existing
    assert refund.refund_to == "original_payment"
    assert refund.amount == payment.total == 235.5
    assert refund.status == "requested"
    assert refund.refund_number.startswith("RF")


def test_non_refundable_fare_becomes_travel_credit(db, alice):
    _payment(db, alice, code="CAN222", refundable=False)

    refund, _, _ = billing_service.request_refund(db, alice.id, "CAN222", "changed plans")

    assert refund.refund_to == "travel_credit"


def test_second_request_returns_the_existing_refund(db, alice):
    _payment(db, alice, code="CAN111")
    first, _, _ = billing_service.request_refund(db, alice.id, "CAN111", "changed plans")

    second, _, was_existing = billing_service.request_refund(db, alice.id, "CAN111", "asking again")

    assert was_existing
    assert second.refund_number == first.refund_number
    assert db.query(Refund).count() == 1


def test_rejected_refund_does_not_block_a_new_request(db, alice):
    _payment(db, alice, code="CAN111")
    first, _, _ = billing_service.request_refund(db, alice.id, "CAN111", "changed plans")
    first.status = "rejected"
    db.commit()

    second, _, was_existing = billing_service.request_refund(db, alice.id, "CAN111", "more details")

    assert not was_existing
    assert second.refund_number != first.refund_number


def test_refund_requires_a_reason(db, alice):
    _payment(db, alice, code="CAN111")
    with pytest.raises(BillingError, match="reason"):
        billing_service.request_refund(db, alice.id, "CAN111", "   ")


def test_other_users_payments_and_refunds_are_invisible(db, alice, bob):
    _payment(db, alice, code="CAN111")
    refund, _, _ = billing_service.request_refund(db, alice.id, "CAN111", "changed plans")

    with pytest.raises(BillingError, match="No payment found"):
        billing_service.get_invoice(db, bob.id, "CAN111")
    with pytest.raises(BillingError, match="No payment found"):
        billing_service.request_refund(db, bob.id, "CAN111", "free money")
    with pytest.raises(BillingError, match="No refund found"):
        billing_service.check_refund_status(db, bob.id, refund.refund_number)
    assert billing_service.list_payments_for_user(db, bob.id) == []


def test_list_payments_includes_active_refund(db, alice):
    _payment(db, alice, _booking(db, alice), code="ABC123", reference="PY000001")
    _payment(db, alice, code="CAN111", reference="PY000002")
    refund, _, _ = billing_service.request_refund(db, alice.id, "CAN111", "changed plans")

    results = {p.confirmation_code: r for p, r in billing_service.list_payments_for_user(db, alice.id)}

    assert results["ABC123"] is None
    assert results["CAN111"].refund_number == refund.refund_number


def test_tools_format_invoice_and_refund(db, alice):
    _payment(db, alice, code="CAN222", refundable=False)
    user_id = str(alice.id)

    invoice = billing_tools.get_invoice.invoke({"confirmation_code": "CAN222", "user_id": user_id})
    refund_text = billing_tools.request_refund.invoke(
        {"confirmation_code": "CAN222", "reason": "trip cancelled", "user_id": user_id}
    )
    payments = billing_tools.list_my_payments.invoke({"user_id": user_id})

    assert "Base fare: USD 200.00" in invoice and "Total: USD 235.50" in invoice
    assert "travel credit" in refund_text
    assert "booking cancelled" in payments and "travel credit" in payments


def test_tool_errors_are_user_facing_messages(alice):
    text = billing_tools.check_refund_status.invoke({"refund_number": "RFNOPE00", "user_id": str(uuid.uuid4())})
    assert text == "No refund found for refund number 'RFNOPE00'."
