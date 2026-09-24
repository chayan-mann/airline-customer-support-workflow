import pytest

from app.agentic_ai.agents import SPECIALIST_AGENTS
from app.agentic_ai.harness.policy import TOOL_RISK, Risk, needs_approval, risk_of


def test_every_agent_tool_has_a_risk_tier():
    # Deny-by-default keeps a forgotten tool safe, but it also makes a new
    # read-only tool nag for approval — so fail loudly here instead.
    missing = {t.name for agent in SPECIALIST_AGENTS for t in agent.TOOLS} - TOOL_RISK.keys()
    assert not missing, f"add these tools to TOOL_RISK in harness/policy.py: {sorted(missing)}"


def test_unknown_tool_is_treated_as_destructive():
    assert risk_of("drop_all_tables") is Risk.DESTRUCTIVE


@pytest.mark.parametrize(
    "tool_names, expected",
    [
        ([], False),
        (["search_faq"], False),
        (["search_faq", "list_my_bookings", "track_bag"], False),
        (["create_booking"], True),
        (["cancel_booking"], True),
        (["search_faq", "move_booking"], True),  # mixed batch is approved as a whole
        (["made_up_tool"], True),
    ],
)
def test_needs_approval(tool_names, expected):
    assert needs_approval([{"name": n} for n in tool_names]) is expected
