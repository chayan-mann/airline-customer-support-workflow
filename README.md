## CUSTOMER SUPPORT AGENT

A local, LangGraph-based customer support agent backed by Ollama. It
answers support questions (shipping, returns, refunds, billing, account,
cancellations) by retrieving relevant articles from a small FAQ knowledge
base (RAG), and pauses for human approval before every tool call.

### Setup

```
pip install -r requirements.txt
ollama pull qwen3.5:9b          # chat model
ollama pull nomic-embed-text    # embedding model for FAQ search
cp .env.example .env            # then fill in OLLAMA_BASE_URL / OLLAMA_MODEL / OLLAMA_EMBED_MODEL
```

### Run

Terminal chat:

```
python -m app.cli
```

API server:

```
uvicorn app.main:app --reload
```

- `POST /chat {"session_id": "...", "message": "..."}` — send a message.
  If the agent wants to search the FAQ, the response comes back with
  `status: "pending_approval"` instead of auto-executing.
- `POST /approve {"session_id": "..."}` — let the pending FAQ search run.
- `POST /reject {"session_id": "..."}` — block the search; the agent is
  told it was denied and won't guess an answer.

### Frontend

A React + Ant Design chat UI lives in `frontend/`. It talks to the API
server above (CORS is enabled for the Vite dev origin).

```
cd frontend
npm install
cp .env.example .env   # VITE_API_BASE_URL, defaults to http://localhost:8000
npm run dev
```

Make sure `uvicorn app.main:app --reload` is running first.

### How it works

`app/graph.py` builds a single-node LangGraph graph with one tool,
`search_faq`, which does similarity search over the mock FAQ documents in
`app/knowledge_base.py` (embedded in-memory via Ollama embeddings). The
graph is compiled with `interrupt_before=["tools"]`, so every tool call
pauses for human approval before it runs — the same human-in-the-loop
pattern you'd use to gate a real mutating action like a refund or
cancellation.
