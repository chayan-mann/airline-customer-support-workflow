from app.agents.baggage import agent as baggage
from app.agents.billing import agent as billing
from app.agents.booking import agent as booking
from app.agents.escalation import agent as escalation
from app.agents.general import agent as general

SPECIALIST_AGENTS = [booking, baggage, billing, general]
