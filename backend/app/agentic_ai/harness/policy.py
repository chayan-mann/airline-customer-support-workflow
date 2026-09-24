"""Security layer: risk tier per tool, deciding which tool calls run straight
away and which pause for human approval."""

from enum import Enum


class Risk(str, Enum):
    READ = "read"                # no side effects — runs without approval
    WRITE = "write"              # changes data — needs approval
    DESTRUCTIVE = "destructive"  # can't be undone — needs approval, shown as dangerous


TOOL_RISK: dict[str, Risk] = {
    # shared
    "search_faq": Risk.READ,
    # booking
    "list_my_bookings": Risk.READ,
    "search_flights": Risk.READ,
    "find_alternative_flights": Risk.READ,
    "list_available_seats": Risk.READ,
    "select_seat": Risk.WRITE,
    "move_booking": Risk.WRITE,
    "create_booking": Risk.WRITE,
    "cancel_booking": Risk.DESTRUCTIVE,
    # baggage
    "list_my_baggage": Risk.READ,
    "track_bag": Risk.READ,
    "check_claim_status": Risk.READ,
    "report_baggage_issue": Risk.WRITE,
    # billing
    "list_my_payments": Risk.READ,
    "get_invoice": Risk.READ,
    "check_refund_status": Risk.READ,
    "request_refund": Risk.WRITE,
}


def risk_of(tool_name: str) -> Risk:
    # Deny by default: a tool missing from TOOL_RISK is treated as the
    # strictest tier, so forgetting to classify a new tool asks for approval
    # instead of letting it run unchecked.
    return TOOL_RISK.get(tool_name, Risk.DESTRUCTIVE)


def needs_approval(tool_calls: list[dict]) -> bool:
    """True if any call in the batch has side effects. A mixed batch (read +
    write) is approved as a whole."""
    return any(risk_of(tc["name"]) != Risk.READ for tc in tool_calls)


def unclassified_tools(tools) -> list[str]:
    """Names of tools with no TOOL_RISK entry (checked once at graph build)."""
    return [t.name for t in tools if t.name not in TOOL_RISK]
