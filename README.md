## CUSTOMER SUPPORT AGENT

A local, LangGraph-based customer support agent backed by Ollama, wrapped
in an [agent harness](#agent-harness) that adds tracing, error handling,
and safety limits to every run. It answers support questions (shipping,
returns, refunds, billing, account, cancellations) by retrieving relevant
articles from a small FAQ knowledge base (RAG), and pauses for human
approval before any tool call that changes data.

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
questions. Read-only tool calls run straight away; any tool call that
changes data pauses for explicit human approval/rejection before it
actually executes (see [Agent harness](#agent-harness)).

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
- `search_flights` → `list_available_seats` → `create_booking` — the same
  token-enforced flow for booking a brand-new flight.
- `cancel_booking` — cancel a booking (irreversible, shown to the reviewer
  as a red confirmation card).

### Baggage agent

`list_my_baggage`, `track_bag`, `report_baggage_issue` (files a claim),
and `check_claim_status`, backed by the checked-bags and baggage-claims
tables.

`billing` and `general` currently only have `search_faq` — they don't yet
have their own domain-specific tools.

## Agent harness

`backend/app/agentic_ai/harness/` is a thin control layer between the
agents and the outside world. Agents and tools don't know it exists: it's
attached to each graph run through `run_config()`, plus a few wrappers
applied where the graph is built.

### Security — tool risk tiers (`harness/policy.py`)

Every tool is listed in `TOOL_RISK` with one of three tiers:

| Tier | Behavior | Tools |
|---|---|---|
| `read` | Runs straight away | `search_faq`, `list_my_bookings`, `search_flights`, `find_alternative_flights`, `list_available_seats`, `list_my_baggage`, `track_bag`, `check_claim_status` |
| `write` | Pauses for approval | `select_seat`, `move_booking`, `create_booking`, `report_baggage_issue` |
| `destructive` | Pauses for approval, red card in the UI | `cancel_booking` |

Each specialist has two tool nodes: `<agent>_read_tools` (no pause) and
`<agent>_tools` (paused with `interrupt_before`). If the model requests a
mix of read and write calls in one step, the whole batch goes to approval.
Each pending tool call sent to the frontend carries its `risk`, which
drives the confirmation card's styling.

**Deny by default:** a tool missing from `TOOL_RISK` is treated as
`destructive`, and an `unclassified_tools` warning is logged at startup.
When you add a tool, add it to `TOOL_RISK`.

### Reliability (`harness/reliability.py`, `harness/__init__.py`)

- **Tool errors don't crash the turn.** Bad arguments from the model come
  back as a "fix the arguments and try again" message; any other exception
  (DB down, a bug) comes back as an "internal error — don't retry, tell
  the user" message, so the model never blindly retries a write.
- **LLM timeout and retries.** Each Ollama request times out after
  `OLLAMA_TIMEOUT_S` seconds (default 60); timeouts and connection errors
  (only those) are retried with jittered backoff, up to 3 attempts total. The intent
  classifier also retries malformed structured output. Tools are never
  retried automatically.
- **Classifier fallback.** If intent classification still fails, the
  message goes to the `general` agent instead of erroring.
- **Step limit.** Each run is capped at `RECURSION_LIMIT` (25) graph
  steps, about 11 tool rounds. A runaway loop ends with a short apology to
  the user, any unanswered tool calls are closed, and the chat keeps
  working normally.

### Observability (`harness/observability.py`)

A LangChain callback handler (`HarnessTracer`) records every graph run —
each message, approval, and rejection — as structured JSON lines, written
both to stdout and to `backend/logs/harness.jsonl` (rotated at 10 MB, 5
backups kept, git-ignored).

| Event | Fields |
|---|---|
| `node_start` | graph node, step number |
| `llm_end` / `llm_error` | node, latency, input/output tokens, tools requested |
| `tool_start` / `tool_end` / `tool_error` | tool, args, result, latency, ok |
| `turn_summary` | outcome (`ok`, `pending_approval`, `step_limit`, `error`, `disconnected`), total latency, node path, LLM calls and tokens, tool calls, errors |
| `classifier_fallback` | the classification error |
| `unclassified_tools` | tools missing from `TOOL_RISK` (at startup) |

Every per-run line carries `trace_id`, `chat_id`, `user_id`, and `kind`
(`message` / `approve` / `reject`); `classifier_fallback` and
`unclassified_tools` are standalone lines without them. Some handy queries:

```bash
# one summary line per turn
jq -c 'select(.event=="turn_summary")' backend/logs/harness.jsonl

# everything for one chat
jq -c 'select(.chat_id=="<chat-id>")' backend/logs/harness.jsonl

# failed tool calls
jq -c 'select(.event=="tool_error")' backend/logs/harness.jsonl

# average turn latency (ms)
jq -s '[.[] | select(.event=="turn_summary") | .total_ms] | add/length' backend/logs/harness.jsonl
```

Tool args and results are logged (truncated to 200 characters), so the
log contains personal data such as passenger names — mask it before
shipping logs anywhere shared.


## Tests

```bash
cd backend
venv/bin/pip install -r requirements-dev.txt
venv/bin/pytest
```

The suite (`backend/tests/`) runs the real graph and harness in about a
second with Postgres, the FAQ embeddings, and Ollama replaced by in-memory
fakes, and scripted model replies. It covers the approval flow (read vs.
write routing, approve, reject), the step limit, tool error handling, LLM
retries and the classifier fallback, and the tracer's events. A tool added
to an agent without a `TOOL_RISK` entry fails the suite.

### Classifier eval (real model)

`backend/evals/classifier_eval.py` runs 32 labelled messages
(`classifier_cases.jsonl`) through the production intent classifier
against your local Ollama and reports accuracy per intent. It needs Ollama,
not Postgres, and exits non-zero below `--min-accuracy` (default 85%), so
use it to check prompt or model changes:

```bash
cd backend
venv/bin/python -m evals.classifier_eval
```
