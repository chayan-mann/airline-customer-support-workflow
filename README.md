## CUSTOMER SUPPORT AGENT

A local, LangGraph-based customer support agent backed by Ollama. It
answers support questions (shipping, returns, refunds, billing, account,
cancellations) by retrieving relevant articles from a small FAQ knowledge
base (RAG), and pauses for human approval before every tool call.

## Current functionality

### Architecture

- **Backend**: FastAPI + SQLAlchemy (Postgres) + LangGraph, orchestrating a
  small multi-agent graph. Ollama runs the chat model (`qwen3.5:9b` by
  default) and embeddings (`nomic-embed-text`) locally — configurable via
  `OLLAMA_MODEL` / `OLLAMA_EMBED_MODEL` / `OLLAMA_BASE_URL` in `.env`.
- **Frontend**: React + Vite + antd.
- **Persistence**: a single Postgres database holds both the app's own
  tables (users, chats, flights, bookings, seats, flight-selection tokens)
  and LangGraph's own conversation checkpoints — schema is managed
  entirely through Alembic migrations (`backend/alembic/`), no
  `create_all()` anywhere.

### Auth & chats

- JWT auth via an httpOnly cookie (`/auth/register`, `/auth/login`,
  `/auth/logout`, `/auth/me`).
- Chats are created, listed, renamed, and deleted (`/chats` routes). A
  chat's id doubles as its LangGraph `thread_id`, so deleting a chat also
  cleans up its checkpointed conversation state.
- A chat's first message triggers a one-off LLM call that generates a
  short title for it automatically (skipped if you've already renamed the
  chat yourself before sending anything).
- Sending a message, approving, or rejecting a pending tool call all
  stream live progress (which graph step is running, which tool is being
  called) instead of blocking silently until the final reply.

### Agent routing

An intent classifier routes each message to one specialist: `booking`,
`baggage`, `billing`, `general`, or `escalate` (a fixed hand-off message,
no LLM). Every specialist also has `search_faq` for general policy
questions. Any tool call that mutates data pauses for explicit
human approval/rejection before it actually executes.

### Booking agent

The most built-out specialist — all backed by real Postgres data (flights,
seats, bookings), scoped to the authenticated user server-side (never a
value the model can supply or forge):

- `list_my_bookings` — every booking on the user's account.
- `find_alternative_flights` → `list_available_seats` →
  `move_booking` — a guided, token-enforced flow to change a booking's
  flight/date: each step hands back a short-lived, single-use token that
  the next step requires, so the model can't skip straight to
  `move_booking` with a made-up flight or seat.
- `select_seat` — change the seat on the current flight (no date change),
  validated against real seat availability.

`baggage`, `billing`, and `general` currently only have `search_faq` —
they don't yet have their own domain-specific tools.

