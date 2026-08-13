# Misinformation Shield

**Verify before you believe.**

An AI-powered, multi-agent fact-checking app. Paste in a claim, headline,
or link and nine independent agents research it against live sources and
a knowledge base, weigh supporting vs. contradicting evidence, and hand
back a traceable, evidence-backed verdict with a confidence score.

This build is a single Flask app: server-rendered pages (`templates/`)
plus a JSON API, no Node.js or separate frontend to run.

```
Claim Extraction → Claim Analysis → (Web Research + Knowledge Base, in parallel)
  → Evidence → Source Credibility → Contradiction Check → Verification
  → Report Generation
```

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env      # defaults to demo/mock mode — no API keys needed
python app.py
```

Open **http://localhost:8000**. Click **Open a case**, paste in any claim,
and watch the nine agents work it in real time.

That's it — everything (LLM, search, embeddings, vector store, database)
runs on safe in-memory/mock providers out of the box, so the whole
pipeline is exercised with zero API keys. Because the mock search
provider returns zero fabricated results by design, claims resolve to
**unverifiable** until you plug in a real search provider (see below) —
that's the app correctly refusing to guess, not a bug.

## Project layout

```
misinformation-shield/
├── app.py              Flask entrypoint — run with `python app.py`
├── worker.py            Optional RQ worker for production task queue (needs REDIS_URL)
├── config.py            Central env-driven configuration
├── requirements.txt
├── .env.example          Copy to .env
├── templates/            Jinja2 pages (served by Flask)
│   ├── base.html          Shared shell: nav, footer, fonts
│   ├── index.html         Landing page + quick-verify box
│   ├── verify.html        Full "open a case" form
│   ├── investigation.html Live progress + verdict/evidence view
│   ├── investigations.html Case log (history)
│   └── about.html         How the pipeline works
├── static/
│   ├── css/style.css      All styling
│   └── js/app.js          API calls + page interactivity (fetch, no framework)
├── agents/                Nine pipeline agents + orchestrator
├── services/               Provider abstractions (LLM/search/embeddings/Pinecone/Supabase)
├── routes/                  REST API blueprints, mounted under /api/*
└── utils/                    Auth, validation, demo data
```

The templates never talk to the agent pipeline directly — they call the
same `/api/*` JSON endpoints the routes above expose, from
`static/js/app.js`, using the fixed `demo-token` bearer token that
`DEMO_MODE` accepts (see `utils/auth.py`). That keeps the split clean: one
Flask process, one `/api` surface, pages are just another client of it.

## How the pages map to the API

| Page | Route | Talks to |
|---|---|---|
| Landing | `GET /` | `POST /api/investigations` (quick-verify box) |
| Open a case | `GET /verify` | `POST /api/investigations` |
| Case detail | `GET /investigations/<id>` | `GET /api/investigations/<id>` (polled every 1.5s until done) |
| Case log | `GET /investigations` | `GET /api/investigations` |
| PDF export | button on case detail | `GET /api/reports/<id>/export` |

## Configuration

Everything lives in one `.env` file at the project root (`config.py` loads
it automatically). Leaving a section blank keeps that piece on its
mock/in-memory fallback — the app stays fully runnable either way.

```
SECRET_KEY=dev-secret-change-me
FLASK_DEBUG=true
DEMO_MODE=true          # local dev only — see below

# Real providers (all optional):
SUPABASE_URL= / SUPABASE_SERVICE_ROLE_KEY= / SUPABASE_JWT_SECRET=
LLM_PROVIDER=groq / LLM_API_KEY= / LLM_MODEL=
PINECONE_API_KEY= / PINECONE_INDEX=
SEARCH_PROVIDER=tavily / SEARCH_API_KEY=
EMBEDDING_PROVIDER= / EMBEDDING_API_KEY=
REDIS_URL=              # production task queue, see below
```

**LLM (Groq):** get a key at [console.groq.com](https://console.groq.com),
set `LLM_API_KEY` and `LLM_MODEL`.

**Search (Tavily, recommended):** get a key at
[tavily.com](https://tavily.com), set `SEARCH_PROVIDER=tavily` and
`SEARCH_API_KEY`. Without this, every investigation resolves to
`unverifiable` on purpose (see "Anti-hallucination design" below).

**Embeddings:** either a free local [Ollama](https://ollama.com) install
(`EMBEDDING_PROVIDER=ollama`, `ollama pull nomic-embed-text`, `ollama
serve`, no key needed), or any hosted OpenAI-compatible endpoint.

**Supabase / Pinecone:** optional. Without them the app uses safe
in-memory fallbacks that behave the same way for a single-process local
run — data just doesn't survive a restart.

## Auth model

There is no login screen in this build. `DEMO_MODE=true` (the default)
treats every visitor as one shared demo user — fine for local use and
demos, **never for a public deployment**. To add real per-user auth,
configure `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` / `SUPABASE_JWT_SECRET`
and issue real Supabase-signed JWTs from wherever you handle login; the
backend in `utils/auth.py` will verify them instead of trusting the demo
token. `GET /api/health` always reports which auth mode is active.

## Anti-hallucination design

- The verification agent never invents evidence — no search results means
  the verdict is `unverifiable`, never a guess.
- Thin evidence (fewer than ~3 items) automatically caps the confidence
  score.
- A dedicated contradiction agent runs a second, deliberately adversarial
  round of searches (`"<claim> false"`, `"<claim> debunked"`, `"<claim>
  fact check"`) so disconfirming evidence isn't under-surfaced.
- Source credibility is a weight on confidence, never a verdict override.

## Running in production

```bash
gunicorn -w 4 -b 0.0.0.0:8000 app:app
```

Set real env vars as server-side secrets, and set `DEMO_MODE=false` with
real Supabase credentials configured — see "Auth model" above.

### Production task queue (RQ + Redis)

By default, investigations run on an in-process background thread — API
calls still return immediately, but a job is lost if the process restarts
and doesn't coordinate across multiple instances. Fine for local use.

For real traffic, set `REDIS_URL` and run a worker alongside the app:

```bash
# terminal 1
python app.py
# terminal 2 — separate worker process (requires real Supabase config,
# since the in-memory fallback is process-local and a worker in a
# different process can't see investigations created by the API process)
python worker.py
```

## Not yet wired into this UI

The API supports document uploads to the knowledge base and an admin
statistics endpoint (`routes/documents.py`, `routes/admin.py`) — they're
available under `/api/documents` and `/api/admin/*` if you want to build
pages for them, but this template set doesn't include screens for them
yet.

---

**Disclaimer** shown on every generated report: *This is an AI-assisted
assessment based on available evidence. It is not an absolute
determination of truth.*
