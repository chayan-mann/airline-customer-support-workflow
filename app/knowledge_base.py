"""Mock airline customer support FAQ knowledge base with in-memory vector search."""

import os

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_ollama import OllamaEmbeddings

load_dotenv()

FAQ_DOCS = [
    Document(
        page_content=(
            "Booking & Reservations: You can book flights online, through "
            "our mobile app, or by calling reservations. Fares can be held "
            "for 24 hours without payment on most itineraries. Group "
            "bookings of 10 or more passengers must be made through our "
            "group travel desk and may qualify for special rates."
        ),
        metadata={"topic": "booking_reservations"},
    ),
    Document(
        page_content=(
            "Check-In: Online and mobile check-in opens 24 hours before "
            "departure and closes 60 minutes before domestic flights or 90 "
            "minutes before international flights. Airport counter "
            "check-in closes 45 minutes before domestic departures and 60 "
            "minutes before international departures. Your boarding pass "
            "can be added to a mobile wallet or printed at a kiosk."
        ),
        metadata={"topic": "check_in"},
    ),
    Document(
        page_content=(
            "Checked Baggage Allowance: Economy passengers may check 1 bag "
            "up to 50 lbs (23 kg) for $35. A second checked bag costs $45. "
            "Bags over 50 lbs or over 62 linear inches incur additional "
            "overweight/oversize fees. Elite frequent flyer members and "
            "eligible credit cardholders get their first checked bag free. "
            "Carry-on bags must not exceed 22 x 14 x 9 inches, plus one "
            "personal item."
        ),
        metadata={"topic": "baggage_allowance"},
    ),
    Document(
        page_content=(
            "Lost, Delayed, or Damaged Baggage: Report missing or damaged "
            "baggage to the baggage service counter before leaving the "
            "airport, or within 24 hours online. Delayed bags are typically "
            "located and delivered within 24-48 hours at no cost to you. "
            "Claims for damaged or lost baggage must be filed within 7 days "
            "of travel for domestic flights."
        ),
        metadata={"topic": "baggage_lost_damaged"},
    ),
    Document(
        page_content=(
            "Flight Changes: Most tickets allow free changes up to 24 hours "
            "before departure; changes made after that may incur a fare "
            "difference but no change fee on most fare classes. Basic "
            "Economy tickets are generally not changeable. All tickets "
            "booked directly with us can be cancelled free of charge within "
            "24 hours of purchase if the booking was made 7 or more days "
            "before departure."
        ),
        metadata={"topic": "flight_changes"},
    ),
    Document(
        page_content=(
            "Delays & Cancellations: If we delay your flight by more than 3 "
            "hours or cancel it, you'll be rebooked on the next available "
            "flight at no charge, or you may request a full refund if you "
            "choose not to travel. Meal vouchers are provided for "
            "controllable delays over 3 hours spanning a mealtime, and "
            "hotel accommodation is provided for overnight delays caused by "
            "the airline."
        ),
        metadata={"topic": "delays_cancellations"},
    ),
    Document(
        page_content=(
            "Refunds: Refundable tickets are refunded to the original "
            "payment method within 7-10 business days of a cancellation "
            "request. Non-refundable tickets are generally issued as a "
            "travel credit for future use instead of a cash refund, except "
            "when the airline cancels or significantly changes the flight."
        ),
        metadata={"topic": "refunds"},
    ),
    Document(
        page_content=(
            "Seat Selection & Upgrades: Standard seats can be selected free "
            "of charge at booking or check-in, subject to availability. "
            "Extra-legroom and preferred seats can be purchased for an "
            "additional fee. Upgrades to premium cabins can be requested "
            "using cash, miles, or complimentary elite upgrade certificates, "
            "and are confirmed in order of elite status and fare class."
        ),
        metadata={"topic": "seat_selection"},
    ),
    Document(
        page_content=(
            "Frequent Flyer Program: Members earn miles based on ticket "
            "price and fare class, redeemable for flights, upgrades, and "
            "partner rewards. Elite status tiers are earned through annual "
            "qualifying miles or segments and unlock perks like free "
            "checked bags, priority boarding, and complimentary upgrades."
        ),
        metadata={"topic": "frequent_flyer"},
    ),
    Document(
        page_content=(
            "Special Assistance: We provide wheelchair service, priority "
            "boarding, and assistance for passengers with disabilities at "
            "no charge — request this at booking or at least 48 hours "
            "before departure for guaranteed accommodation. Unaccompanied "
            "minors ages 5-14 can travel with paid supervision service. "
            "Trained service animals may travel in the cabin at no charge "
            "with advance notice."
        ),
        metadata={"topic": "special_assistance"},
    ),
    Document(
        page_content=(
            "Traveling with Pets: Small cats and dogs may travel in an "
            "approved carrier under the seat in front of you for a pet fee, "
            "on a first-come, first-served basis with limited spots per "
            "flight. Larger pets can travel as checked cargo on select "
            "routes. Some breeds and destinations have restrictions, so "
            "check requirements before booking."
        ),
        metadata={"topic": "pet_travel"},
    ),
    Document(
        page_content=(
            "Travel Documents: Domestic travelers need a valid government "
            "ID; starting with the REAL ID enforcement date, a REAL "
            "ID-compliant license or passport is required to fly within the "
            "US. International travel requires a passport valid for at "
            "least 6 months beyond your travel dates, and may require a "
            "visa depending on destination and nationality — it's your "
            "responsibility to confirm entry requirements."
        ),
        metadata={"topic": "travel_documents"},
    ),
    Document(
        page_content=(
            "In-Flight Services: Complimentary wifi messaging is available "
            "on most aircraft, with full wifi access available for "
            "purchase. Seatback or streaming entertainment is offered on "
            "most flights. Snacks and beverages are complimentary in "
            "economy on longer flights; special meals (vegetarian, kosher, "
            "gluten-free, etc.) can be requested at least 24 hours before "
            "departure."
        ),
        metadata={"topic": "inflight_services"},
    ),
    Document(
        page_content=(
            "Payment & Billing: We accept Visa, Mastercard, American "
            "Express, Discover, PayPal, and payment with miles plus cash on "
            "eligible bookings. Ticket prices include base fare plus taxes "
            "and government fees, itemized at checkout. If you see a "
            "duplicate or unrecognized charge, it's often a temporary "
            "authorization hold that clears within a few business days; "
            "contact support with your confirmation number if it doesn't."
        ),
        metadata={"topic": "payment_billing"},
    ),
    Document(
        page_content=(
            "Contact & Support Hours: Our support team is available by "
            "phone and chat 24/7 for urgent travel-day issues, and by email "
            "for general questions with a response time under 24 hours. "
            "Airport ticket counters typically open 3 hours before the "
            "first departure of the day and remain staffed through the last "
            "departure."
        ),
        metadata={"topic": "contact"},
    ),
]

embeddings = OllamaEmbeddings(
    model=os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text"),
    base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
)

vector_store = InMemoryVectorStore(embeddings)
vector_store.add_documents(FAQ_DOCS)


def search(query: str, k: int = 3) -> list[Document]:
    """Return the k most relevant FAQ documents for the given query."""
    return vector_store.similarity_search(query, k=k)
