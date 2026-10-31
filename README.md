# AI Job Seeker Agent

An autonomous/semi-autonomous agent that parses resumes, improves candidate profiles, aggregates job/internship listings across MNCs and startups, runs LLM-driven skill-gap analysis, and assists (but does not blindly automate) the application step via a Playwright pre-fill browser.

## 1. System Architecture

```
┌────────────────────┐        HTTP/JSON         ┌──────────────────────────┐
│   Streamlit (app.py)│ ───────────────────────▶ │   FastAPI (main.py)      │
│  - Resume upload UI │ ◀─────────────────────── │  - REST endpoints        │
│  - Job search UI    │                          │  - Orchestrates agent,   │
│  - Gap analysis UI   │                          │    scraper, DB          │
│  - Apply-assistant   │                          └───────────┬──────────────┘
│    trigger button    │                                      │
└──────────────────────┘                                      │
                                                                │
                    ┌───────────────────────────────────────────┼───────────────────────────┐
                    │                                            │                            │
                    ▼                                            ▼                            ▼
        ┌───────────────────────┐                  ┌───────────────────────┐     ┌────────────────────────┐
        │ agent.py (LangChain)   │                  │ scraper.py             │     │ apply_assistant.py      │
        │ - Groq (Llama 3.3)     │                  │ - SerpApi Google Jobs  │     │ - Playwright, headed    │
        │ - parse_resume()       │                  │   (title/company/desc/ │     │   browser               │
        │ - improve_profile()    │                  │   actual apply URL)    │     │ - Fills name/email/     │
        │ - analyze_gap()        │                  └───────────┬────────────┘     │   GitHub/resume upload  │
        └───────────┬────────────┘                              │                  │ - Human clicks Submit   │
                    │                                            │                  └────────────┬────────────┘
                    │                                            │                                │
                    ▼                                            ▼                                │
        ┌───────────────────────────────────────────────────────────────────────────────────────────┐
        │                              PostgreSQL (+ pgvector)                                       │
        │  users │ profiles (parsed resume JSONB) │ jobs (+ embedding) │ gap_analyses │ applications  │
        └───────────────────────────────────────────────────────────────────────────────────────────┘
```

**Why this shape**

- **Streamlit talks only to FastAPI**, never directly to the DB or the LLM. This keeps the UI stateless/swappable and lets the same backend later serve a real frontend (React, mobile, etc.) with zero changes.
- **FastAPI is the orchestrator.** It never calls the LLM or scraper directly with business logic inline — it delegates to `agent.py` (reasoning) and `scraper.py` (data acquisition), and persists everything through SQLAlchemy models.
- **`agent.py` isolates all prompt engineering and LLM I/O.** Every LLM call returns a validated Pydantic object (via LangChain's tool-calling structured output), so a bad/partial LLM response fails loudly (Pydantic `ValidationError`) instead of corrupting the DB with malformed JSON.
- **`scraper.py` uses the SerpApi Google Jobs API**, not raw scraping of LinkedIn/Indeed/etc. Those sites' ToS generally prohibit automated scraping and they aggressively block headless browsers/CAPTCHA-gate scraping traffic. SerpApi aggregates Google for Jobs (which itself pulls from LinkedIn, Indeed, Glassdoor, and individual company ATS boards like Greenhouse/Lever) and returns the **actual employer apply URL**, which is exactly what's needed downstream. This is the compliant, reliable, production path.
- **`apply_assistant.py` is intentionally semi-automated.** Modern ATS platforms (Workday, Greenhouse, Lever, iCIMS) use dynamic forms, CAPTCHAs, and bot-detection. Fully auto-submitting applications is fragile, easy to break silently, and can violate a given employer's terms of use. Instead, Playwright launches a **visible, headed browser**, best-effort fills known fields (name, email, phone, LinkedIn, GitHub, resume upload), and stops — a human reviews and clicks Submit. This is the reliable, ToS-respecting middle ground the spec calls for.

## 2. Database Schema

See [`sql/schema.sql`](sql/schema.sql). Summary:

| Table | Purpose |
|---|---|
| `users` | Account identity (email-based; swap in real auth later) |
| `profiles` | One resume per user: raw text + LLM-parsed structured JSON (`skills`, `experience`, `education`, `contact_info`) |
| `jobs` | Scraped listings: title, company, description, `apply_url` (the actual employer link), source, optional pgvector `embedding` for future semantic matching |
| `gap_analyses` | Result of comparing a profile against a job: match %, missing requirements, recommendations — all JSONB so the LLM's structured output maps 1:1 |
| `applications` | Tracks state per (user, job): `saved → prefilled → applied → interview/offer/rejected` |

`pgvector` is enabled so `jobs.embedding` can later back semantic "find similar jobs to what I'm good at" search — the gap-analysis flow itself uses the LLM directly and doesn't require it, so it's optional infrastructure for a v2 feature, not a hard dependency today.

## 3. Project Layout

```
job_seeker_bot/
├── README.md
├── .env.example
├── requirements.txt
├── sql/schema.sql
├── backend/
│   ├── config.py            # env-driven settings
│   ├── database.py          # SQLAlchemy engine/session
│   ├── models.py            # ORM tables
│   ├── schemas.py           # API request/response DTOs
│   ├── resume_parser.py     # PDF -> text
│   ├── agent.py             # LangChain + Gemini: parsing, improvement, gap analysis
│   ├── scraper.py           # SerpApi Google Jobs client
│   ├── apply_assistant.py   # Playwright pre-fill assistant
│   └── main.py               # FastAPI app
└── frontend/
    └── app.py                # Streamlit dashboard
```

## 4. Setup

```bash
# 1. Postgres (with pgvector) — via Docker is easiest:
docker run --name jsb-postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=job_seeker_bot -p 5432:5432 -d ankane/pgvector

# 2. Python deps
python -m venv .venv && source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
playwright install chromium

# 3. Configure
cp .env.example .env
# then fill in GROQ_API_KEY and SERPAPI_API_KEY

# 4. Load schema
psql "$DATABASE_URL" -f sql/schema.sql
# (main.py also auto-creates tables on startup via SQLAlchemy for local dev convenience)

# 5. Run backend
uvicorn backend.main:app --reload --port 8000

# 6. Run frontend (separate terminal)
streamlit run frontend/app.py
```

Get a SerpApi key at https://serpapi.com (Google Jobs engine) and a Groq API key (free tier, no card required) at https://console.groq.com/keys.

## 5. Notes & Trade-offs

- **Model:** defaults to `llama-3.3-70b-versatile` (`GROQ_MODEL` env var) via Groq — free tier, no billing setup required, no quota-provisioning gotchas. Swap `GROQ_MODEL` for any other model Groq hosts; nothing else in the code needs to change.
- **The apply assistant must run where a display exists** (your laptop), since Playwright launches a real, visible Chromium window for the human to review. It is designed to be triggered from the Streamlit app itself (running locally) rather than from a server-hosted FastAPI instance.
- **No destructive automation:** the assistant never clicks Submit. It fills fields and stops.
#   j o b - s e e k i n g - a g e n t  
 