# Portfolio Project Inventory

| Project | Type | Tech stack | Status | Last updated |
|---|---|---|---|---|
| AI Job Seeker Agent (`job_seeker_bot`) | Web app / AI-assisted job-search tool | Python, Streamlit, FastAPI, PostgreSQL, SQLAlchemy, LangChain/Groq, SerpApi, Playwright | Prototype (inferred) | Not found (no Git history available) |

## AI Job Seeker Agent

### 1. Basics

- **Project name:** `job_seeker_bot`
- **Display name:** AI Job Seeker Agent
- **Tagline:** An AI-assisted job search workspace that turns a resume into structured career guidance and a more focused application workflow.
- **Description:** The application helps job seekers extract structured profile information from a PDF resume, get LLM-generated resume feedback, and discover jobs through Google Jobs results supplied by SerpApi. It compares resume vocabulary with job listings, provides a separate LLM-generated skill-gap analysis, and tracks saved applications. Its browser assistant fills recognizable application fields but deliberately leaves review and submission to the user.
- **Project type:** Web application with an API backend and browser automation.
- **Status:** **Prototype (inferred).** The code includes a local setup and end-to-end feature flows, but there is no deployment configuration, production hosting evidence, test suite, or Git activity in this workspace. The README describes some database functionality (such as embeddings) as optional or future work.

### 2. Timeline

| Measure | Finding |
|---|---|
| First commit date | Not found — this directory is not a Git repository |
| Last commit date | Not found |
| Total commits | Not found |
| Contributors | Not found |
| Author's share of commits | Not found |

### 3. Tech stack

- **Languages:** Python and SQL.
- **UI and API:** Streamlit frontend; FastAPI REST API; Uvicorn ASGI server.
- **AI and validation:** LangChain with `langchain-groq`; Groq-hosted Llama 3.3 model by default; Pydantic models for validated structured LLM output; Pydantic Settings for environment-driven configuration.
- **Database:** PostgreSQL via SQLAlchemy and `psycopg2-binary`; JSONB columns store parsed profiles and analysis results. The schema enables the PostgreSQL `vector` extension and defines a 1536-dimension embedding column as optional/future infrastructure; the inspected job ranking uses lexical overlap rather than vector search.
- **Job discovery and page retrieval:** SerpApi Google Jobs engine; Requests; BeautifulSoup for extracting readable text and page titles from user-provided job links.
- **Resume and document handling:** pdfplumber for PDF text extraction; FPDF2 and python-docx for downloadable PDF and DOCX resumes; `python-multipart` is declared for upload handling.
- **Browser automation:** Playwright with Chromium, launched in a visible browser for human-reviewed application prefill.
- **Other declared dependencies:** NumPy, HTTPX, `python-dotenv`, and the `pgvector` Python package appear in `requirements.txt`; direct use of NumPy and HTTPX was not found in application source.
- **Database/development setup:** The README documents running PostgreSQL with pgvector in Docker for local development. No CI/CD workflow, deployment platform, or test framework was found.

### 4. Features

- Accepts PDF resumes, extracts selectable text, and asks the LLM to produce a structured candidate profile.
- Shows the parsed profile and generates resume feedback, including missing keywords, formatting issues, and concrete suggestions.
- Produces downloadable resume documents in PDF and DOCX formats.
- Searches Google Jobs through SerpApi, persists listings, resolves available employer application links, and deduplicates results using a SHA-256-derived external ID.
- Offers resume-based job ranking using token overlap across skills, past titles, summary, job title, and description. This is a lightweight lexical score, not semantic/vector matching.
- Accepts a user-provided job URL and extracts page title and visible text for downstream analysis.
- Generates an LLM-based skill-gap report with a match percentage, overlapping skills, missing requirements, and recommended actions.
- Lets users add selected gap skills to the profile and download the updated resume.
- Provides a career chat interface with optional parsed-resume context.
- Saves applications and tracks statuses including saved, prefilled, applied, interviewing, offer, and rejected.
- Uses Playwright to best-effort prefill common application fields and upload a resume. The browser remains visible for human review; the assistant does not submit applications.

### 5. Architecture

The Streamlit app calls the FastAPI service over HTTP; the UI does not connect directly to PostgreSQL. FastAPI coordinates request handling and persistence through SQLAlchemy, while dedicated backend modules handle LLM reasoning, job fetching/search, resume parsing, lexical matching, and browser prefill. Resume/profile, job, gap-analysis, and application records are stored in PostgreSQL.

Key folders and files:

- [`frontend/`](frontend/) — Streamlit dashboard, session state, profile and job-search flows, chat, and resume document generation.
- [`backend/main.py`](backend/main.py) — FastAPI routes and orchestration for profiles, jobs, gap analyses, chat, applications, and prefill.
- [`backend/agent.py`](backend/agent.py) — LangChain/Groq prompts and Pydantic structured-output models for resume parsing, feedback, and gap analysis.
- [`backend/scraper.py`](backend/scraper.py) — SerpApi Google Jobs client and listing normalization.
- [`backend/job_fetcher.py`](backend/job_fetcher.py) — Fetches a supplied job page and extracts its title and readable text.
- [`backend/resume_parser.py`](backend/resume_parser.py) — PDF-to-text extraction.
- [`backend/matching.py`](backend/matching.py) — Resume-token extraction and lexical job relevance scoring.
- [`backend/apply_assistant.py`](backend/apply_assistant.py) — Visible Playwright browser automation for form prefill.
- [`backend/models.py`](backend/models.py) and [`backend/schemas.py`](backend/schemas.py) — SQLAlchemy data models and Pydantic API DTOs.
- [`backend/database.py`](backend/database.py) and [`backend/config.py`](backend/config.py) — Database engine/session and environment-backed settings.
- [`sql/schema.sql`](sql/schema.sql) — PostgreSQL tables, indexes, constraints, and extensions.
- [`requirements.txt`](requirements.txt) — Python dependencies.
- [`README.md`](README.md) — Architecture rationale and local setup instructions.

### 6. Challenges & solutions

- **Keeping model output usable by the application:** LLM operations use structured Pydantic output models, so the application can validate parsed resumes and gap-analysis responses instead of manually consuming arbitrary text.
- **Handling variable job pages:** The URL importer uses a generic title/visible-text extraction approach rather than depending on one ATS page structure, and caps extracted description text for downstream analysis.
- **Avoiding brittle full application automation:** The prefill assistant looks for common field labels/attributes, tolerates fields it cannot recognize, launches a visible browser, and leaves submission to the user.
- **Ranking jobs without an embedding pipeline:** The implemented ranking computes resume/job token overlap; pgvector is present only as optional schema infrastructure for future semantic matching.
- **Handling PDF limitations:** Resume extraction reports an error for empty or unreadable text, including image-only/scanned PDFs that do not yield extractable text.

### 7. Impact & results

- User, application, or job-volume metrics: **Not found**.
- Measured performance, awards, or documented outcomes: **Not found**.
- The code documents an implemented workflow, but this workspace does not provide evidence of production usage or measured impact.

### 8. Links & assets

- **Live/demo URL:** Not found.
- **GitHub/remote URL:** Not found — no Git repository or remote was available.
- **Project documentation:** [`README.md`](README.md); database schema at [`sql/schema.sql`](sql/schema.sql).
- **Service references in the README:** [SerpApi](https://serpapi.com/) and [Groq API keys](https://console.groq.com/keys). These are provider links, not project demos.
- **Screenshots, logo, demo GIF, or video:** Not found.
- **Uploaded documents:** `uploads/` contains user-provided resume PDFs. Their filenames and contents are intentionally omitted; they are user data, not portfolio/demo assets.

### 9. Size

- **Implementation files:** 14 Python/SQL files (13 Python files and one SQL schema).
- **Approximate code size:** 1,463 lines across those Python and SQL files.
- Counts exclude dependency/generated directories and secret-bearing environment files. User-uploaded documents are excluded from source-code size.

## Overall skills profile

Technology counts are project counts; this inventory found one project. Items marked **declared** were listed as dependencies but were not directly observed in the application source.

| Category | Technologies | Projects |
|---|---|---:|
| Languages | Python (1), SQL (1) | 1 each |
| Web/API | Streamlit (1), FastAPI (1), Uvicorn (1) | 1 each |
| AI/LLM and validation | LangChain (1), Groq API (1), Llama 3.3 (1), Pydantic (1), Pydantic Settings (1) | 1 each |
| Data and persistence | PostgreSQL (1), SQLAlchemy (1), JSONB (1), pgvector extension (1; optional/future) | 1 each |
| Job discovery and HTTP | SerpApi Google Jobs (1), Requests (1), BeautifulSoup (1), HTTPX (1; declared) | 1 each |
| Documents and browser automation | pdfplumber (1), FPDF2 (1), python-docx (1), Playwright (1), Chromium (1) | 1 each |
| Development/runtime | Docker (1; documented local setup), psycopg2-binary (1), python-multipart (1), python-dotenv (1; declared), NumPy (1; declared), pgvector Python package (1; declared) | 1 each |

## Suggested featured projects

Only one standalone project was found in the workspace, so there is not enough evidence to recommend three to five distinct projects.

1. **AI Job Seeker Agent** — Strongest portfolio candidate in this directory: it combines a full-stack UI/API, structured LLM workflows, PostgreSQL persistence, third-party job search, document generation, and human-supervised browser automation in one coherent product.
