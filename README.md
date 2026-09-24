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
  tables (users, chats, flights, bookings, seats, flight-selection tokens,
  checked bags, baggage claims, payments, refunds)
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

### Billing agent

- `list_my_payments` — every payment on the account, including for
  cancelled bookings, with any refund in progress.
- `get_invoice` — itemized invoice for one booking (base fare, taxes &
  fees, total, payment method, fare type).
- `request_refund` — refund a *cancelled* booking: refundable fares go back
  to the original payment method, non-refundable fares become travel
  credit (per the Refunds FAQ). Refuses while the booking is still active,
  and returns the existing refund instead of creating a duplicate.
- `check_refund_status` — look up a refund by its number (e.g. `RF4F7K2X`).

Payments outlive their bookings on purpose: `cancel_booking` deletes the
booking row, so `payments.booking_id` is `SET NULL` on delete (NULL means
"booking cancelled") and the confirmation code and flight summary are
snapshotted on the payment. New bookings made through `create_booking`
don't create a payment yet — there's no payment step in that flow.

`general` currently only has `search_faq` — it doesn't yet have its own
domain-specific tools.

### Demo data

```bash
cd backend
alembic upgrade head
python -m app.scripts.seed_bookings   # users, flights, seats, bookings
python -m app.scripts.seed_baggage    # checked bags and baggage claims
python -m app.scripts.seed_billing    # payments and refunds
```

`seed_billing` also adds payments for three already-cancelled bookings
(`CAN111` with a completed refund, `CAN222` non-refundable with no refund
yet, `CAN444` refundable with no refund yet) and one for the second user
(`CAN333`, refund processing), so the refund flow can be tried end to end.

## Agent harness

`backend/app/agentic_ai/harness/` is a thin control layer between the
agents and the outside world. Agents and tools don't know it exists: it's
attached to each graph run through `run_config()`, plus a few wrappers
applied where the graph is built.

### Security — tool risk tiers (`harness/policy.py`)

Every tool is listed in `TOOL_RISK` with one of three tiers:

| Tier | Behavior | Tools |
|---|---|---|
| `read` | Runs straight away | `search_faq`, `list_my_bookings`, `search_flights`, `find_alternative_flights`, `list_available_seats`, `list_my_baggage`, `track_bag`, `check_claim_status`, `list_my_payments`, `get_invoice`, `check_refund_status` |
| `write` | Pauses for approval | `select_seat`, `move_booking`, `create_booking`, `report_baggage_issue`, `request_refund` |
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

### Tool-choice eval (real model)

`backend/evals/tool_choice_eval.py` checks that each specialist agent picks
the right tool with the right arguments, and never takes a forbidden
shortcut — e.g. calling `move_booking` before the user picked a flight and
seat, calling `create_booking` without asking for a passenger name, or
filing a baggage claim without a tag number. Its 28 cases
(`tool_choice_cases.jsonl`) can start mid-conversation, with earlier tool
results in the history, to test later steps of a flow. Only the model's
next step is graded and tools are never executed, so it needs Ollama but
not Postgres.

```bash
cd backend
venv/bin/python -m evals.tool_choice_eval             # all cases
venv/bin/python -m evals.tool_choice_eval --repeat 3  # spot flaky cases
venv/bin/python -m evals.tool_choice_eval --only move-step2-uses-picked-token
```

### Answer-quality eval (real model + LLM judge)

`backend/evals/answer_quality_eval.py` asks each specialist 19 policy
questions (`answer_quality_cases.jsonl`), runs the real agent loop with the
real FAQ search until it replies, then has a judge model grade each reply:

- **correctness** — `correct` / `partial` / `incorrect` against a reference
  answer written from the FAQ.
- **grounded** — whether every policy fact in the reply appears in the FAQ
  text the agent actually retrieved. This catches answers made up from the
  model's general knowledge, which the prompts forbid.

Three cases ask about things the FAQ doesn't cover (lounges, price
matching, surfboards); the right answer there is "I don't have that
information", not an invented policy. The score counts `correct` as 1 and
`partial` as 0.5, and the run fails below `--min-score` (default 75%).

```bash
cd backend
venv/bin/python -m evals.answer_quality_eval
venv/bin/python -m evals.answer_quality_eval --judge-model qwen3.5:27b
venv/bin/python -m evals.answer_quality_eval --only change-fee --show-answers
```

The judge defaults to `EVAL_JUDGE_MODEL`, else `OLLAMA_MODEL`. A judge the
same size as the model being tested tends to be lenient and noisy, so use a
larger one if you can, and read the judge's reasons for failures rather
than trusting the score alone. Needs Ollama (chat and embedding models), not
Postgres.
