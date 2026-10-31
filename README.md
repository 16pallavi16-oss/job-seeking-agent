# AI Job Seeker Agent

A local job-search assistant with a Streamlit dashboard and FastAPI backend. It parses PDF resumes, searches Google Jobs through SerpApi, compares jobs with a resume, tracks applications, and can prefill supported application forms for a person to review.

## Features

- Upload a PDF resume and extract its contact details, skills, experience, and education.
- Get AI-assisted resume feedback and job-specific skill-gap analysis.
- Search job listings through the SerpApi Google Jobs engine, or add a job from its URL.
- Track saved applications and update their status.
- Ask questions about a parsed resume and job search in the chat assistant.
- Optionally prefill application forms in a visible browser. The assistant does not submit applications.

## Architecture

```text
Streamlit dashboard (frontend/app.py)
              |
              | HTTP
              v
FastAPI API (backend/main.py)
       |           |            |
       v           v            v
  LangChain      SerpApi    PostgreSQL
  + Groq       Google Jobs  + SQLAlchemy
```

The API uses SQLAlchemy to create its application tables when it starts. The SQL script also enables PostgreSQL extensions and includes an optional vector column for future use.

## Requirements

- Python 3.10 or newer
- Docker Desktop (or another PostgreSQL server)
- A [Groq API key](https://console.groq.com/keys) for AI features
- A [SerpApi API key](https://serpapi.com/) for job search
- `psql` only if you want to apply the optional SQL schema script manually

## Setup on Windows

Run these commands from the project directory in PowerShell:

```powershell
# Start PostgreSQL with the pgvector extension available
docker run --name jsb-postgres `
  -e POSTGRES_PASSWORD=postgres `
  -e POSTGRES_DB=job_seeker_bot `
  -p 5432:5432 `
  -d ankane/pgvector

# Create and activate a virtual environment
py -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies and the browser used by the application helper
python -m pip install -r requirements.txt
playwright install chromium

# Create your local configuration
Copy-Item .env.example .env
```

Edit `.env` and set `DATABASE_URL`, `GROQ_API_KEY`, and `SERPAPI_API_KEY`. For the Docker command above, the database URL should point to `localhost:5432/job_seeker_bot` and use the `postgres` user and password. Keep `.env` private; it is excluded from Git.

Set `DATABASE_URL` to `postgresql+psycopg2://postgres:postgres@localhost:5432/job_seeker_bot` for the Docker command above. The API creates the tables it needs on startup. If you also want the optional extension and vector-column setup from [`sql/schema.sql`](sql/schema.sql), run the script once before starting the API:

```powershell
psql -h localhost -U postgres -d job_seeker_bot -f sql/schema.sql
```

The SQL script is optional and should only be applied once to a new database. If you skip it, the API creates its application tables automatically.

## Run the application

Start the backend from the project directory:

```powershell
uvicorn backend.main:app --reload --port 8000
```

In a second PowerShell terminal, activate the same virtual environment and start the dashboard:

```powershell
.\.venv\Scripts\Activate.ps1
streamlit run frontend/app.py
```

Open the Streamlit URL shown in the terminal (usually `http://localhost:8501`). The API documentation is available at `http://localhost:8000/docs`.

On macOS or Linux, activate the environment with `source .venv/bin/activate` and copy the configuration with `cp .env.example .env`; the install and run commands are otherwise the same.

## Configuration

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | SQLAlchemy connection URL for PostgreSQL |
| `GROQ_API_KEY` | API key used for resume parsing, feedback, gap analysis, and chat |
| `GROQ_MODEL` | Groq model name; defaults to `llama-3.3-70b-versatile` |
| `SERPAPI_API_KEY` | API key used for Google Jobs search |
| `BACKEND_URL` | Backend URL used by Streamlit; defaults to `http://localhost:8000` |
| `UPLOAD_DIR` | Local directory for uploaded resumes; defaults to `./uploads` |

Job search requires SerpApi. AI features require Groq. The backend can start without either key, but the corresponding features will not work until configured.

## Project layout

```text
.
├── backend/
│   ├── agent.py             # LangChain and Groq features
│   ├── apply_assistant.py   # Visible-browser application form helper
│   ├── config.py            # Environment-based settings
│   ├── database.py          # SQLAlchemy engine and sessions
│   ├── job_fetcher.py       # Fetch job details from a supplied URL
│   ├── main.py              # FastAPI routes
│   ├── matching.py          # Resume-to-job matching
│   ├── models.py            # SQLAlchemy models
│   ├── resume_parser.py     # PDF text extraction
│   ├── schemas.py           # API request and response models
│   └── scraper.py           # SerpApi Google Jobs client
├── frontend/
│   └── app.py               # Streamlit dashboard
├── sql/
│   └── schema.sql           # PostgreSQL schema and optional vector setup
├── .env.example
└── requirements.txt
```

## Privacy and application assistance

Resume files are stored locally in `uploads/`, which is excluded from Git. Resume text is sent to Groq when you use AI features, and job-search queries are sent to SerpApi. Review the providers' policies before using the application with personal data.

The application helper opens a visible Chromium browser and attempts to fill supported fields. Review the form yourself and submit it manually; the helper does not click Submit. Run the backend on the computer with the browser display, not on a headless server, when using this feature.
