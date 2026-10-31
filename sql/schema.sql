-- AI Job Seeker Agent — PostgreSQL schema
-- Requires the pgvector extension for the optional job-embedding column.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto; -- for gen_random_uuid()

CREATE TABLE IF NOT EXISTS users (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email       TEXT UNIQUE NOT NULL,
    full_name   TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row per uploaded resume. parsed_json holds the LLM-extracted structured
-- resume (skills, experience, education, contact_info) so downstream gap
-- analysis never has to re-parse raw text.
CREATE TABLE IF NOT EXISTS profiles (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    resume_file_path  TEXT,
    raw_resume_text   TEXT NOT NULL,
    parsed_json       JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_profiles_user_id ON profiles(user_id);
CREATE INDEX IF NOT EXISTS idx_profiles_parsed_json ON profiles USING GIN (parsed_json);

-- Scraped/aggregated job & internship listings.
CREATE TABLE IF NOT EXISTS jobs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    external_id   TEXT UNIQUE,              -- dedupe key from the source (hash of title+company+apply_url)
    title         TEXT NOT NULL,
    company       TEXT NOT NULL,
    location      TEXT,
    description   TEXT,
    apply_url     TEXT NOT NULL,             -- the actual employer apply link
    source        TEXT NOT NULL DEFAULT 'serpapi_google_jobs',
    job_type      TEXT,                      -- e.g. internship / full-time / contract
    posted_at     TIMESTAMPTZ,
    scraped_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    embedding     vector(1536)               -- optional, for future semantic search
);

CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);
CREATE INDEX IF NOT EXISTS idx_jobs_title ON jobs USING GIN (to_tsvector('english', title));

-- Result of running gap analysis for a (profile, job) pair.
CREATE TABLE IF NOT EXISTS gap_analyses (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id            UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    job_id                UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    match_percentage      INTEGER NOT NULL CHECK (match_percentage BETWEEN 0 AND 100),
    matching_skills       JSONB NOT NULL DEFAULT '[]'::jsonb,
    missing_requirements  JSONB NOT NULL DEFAULT '[]'::jsonb,
    recommendations       JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (profile_id, job_id)
);

CREATE TYPE application_status AS ENUM (
    'saved', 'prefilled', 'applied', 'interviewing', 'offer', 'rejected'
);

CREATE TABLE IF NOT EXISTS applications (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    job_id       UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    status       application_status NOT NULL DEFAULT 'saved',
    notes        TEXT,
    applied_at   TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, job_id)
);

CREATE INDEX IF NOT EXISTS idx_applications_user_id ON applications(user_id);
CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);
