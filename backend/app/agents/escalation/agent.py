NAME = "escalation"

MESSAGE = (
    "This request needs a human specialist to help you safely — connecting "
    "you with a live agent now. Please hold."
)


def node(state):
    return {"messages": [{"role": "assistant", "content": MESSAGE}]}
