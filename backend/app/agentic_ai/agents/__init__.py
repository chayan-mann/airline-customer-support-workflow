from app.agentic_ai.agents.baggage import agent as baggage
from app.agentic_ai.agents.billing import agent as billing
from app.agentic_ai.agents.booking import agent as booking
from app.agentic_ai.agents.escalation import agent as escalation
from app.agentic_ai.agents.general import agent as general

SPECIALIST_AGENTS = [booking, baggage, billing, general]
