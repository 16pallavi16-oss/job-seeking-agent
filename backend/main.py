import hashlib
import logging
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.agent import GapAnalysisResult, ParsedResume, ProfileImprovement, agent
from backend.apply_assistant import ApplicantProfile, prefill_application
from backend.config import settings
from backend.database import Base, engine, get_db
from backend.job_fetcher import JobFetchError, fetch_job_from_url
from backend.matching import resume_tokens, score_job
from backend.models import Application, ApplicationStatus, GapAnalysis, Job, Profile, User
from backend.resume_parser import ResumeParsingError, extract_text_from_pdf
from backend.schemas import (
    AddSkillsRequest,
    ApplicationCreate,
    ApplicationOut,
    ApplicationUpdate,
    ChatRequest,
    ChatResponse,
    GapAnalysisOut,
    GapAnalysisRequest,
    JobFromUrlRequest,
    JobOut,
    JobSearchRequest,
    JobSearchResultOut,
    PrefillRequest,
)
from backend.scraper import JobSourceError, SerpApiJobSource

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Job Seeker Agent API")

Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)


@app.on_event("startup")
def on_startup() -> None:
    # Convenience for local dev. In production, apply sql/schema.sql via a migration tool instead.
    Base.metadata.create_all(bind=engine)


# ---------------------------------------------------------------------------
# Profiles: resume upload, parsing, and standalone profile improvement
# ---------------------------------------------------------------------------


@app.post("/users")
def create_user(email: str, full_name: str | None = None, db: Session = Depends(get_db)) -> dict:
    existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing:
        return {"id": str(existing.id), "email": existing.email}
    user = User(email=email, full_name=full_name)
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"id": str(user.id), "email": user.email}


@app.post("/profiles/upload-resume")
async def upload_resume(user_id: uuid.UUID, file: UploadFile, db: Session = Depends(get_db)) -> dict:
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF resumes are supported.")

    file_bytes = await file.read()
    try:
        resume_text = extract_text_from_pdf(file_bytes)
    except ResumeParsingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    file_path = Path(settings.UPLOAD_DIR) / f"{uuid.uuid4()}_{file.filename}"
    file_path.write_bytes(file_bytes)

    try:
        parsed: ParsedResume = agent.parse_resume(resume_text)
    except Exception as exc:
        logger.exception("Resume parsing via LLM failed")
        raise HTTPException(status_code=502, detail=f"Resume parsing failed: {exc}") from exc

    profile = Profile(
        user_id=user_id,
        resume_file_path=str(file_path),
        raw_resume_text=resume_text,
        parsed_json=parsed.model_dump(mode="json"),
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)

    return {"profile_id": str(profile.id), "parsed_resume": parsed.model_dump(mode="json")}


@app.post("/profiles/{profile_id}/add-skills")
def add_skills(profile_id: uuid.UUID, request: AddSkillsRequest, db: Session = Depends(get_db)) -> dict:
    profile = db.get(Profile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")

    parsed_json = dict(profile.parsed_json)
    skills = list(parsed_json.get("skills") or [])
    for skill in request.skills:
        if skill not in skills:
            skills.append(skill)
    parsed_json["skills"] = skills
    profile.parsed_json = parsed_json

    db.commit()
    db.refresh(profile)
    return {"profile_id": str(profile.id), "parsed_resume": profile.parsed_json}


@app.get("/profiles/{profile_id}/improve")
def improve_profile(profile_id: uuid.UUID, db: Session = Depends(get_db)) -> ProfileImprovement:
    profile = db.get(Profile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")

    parsed = ParsedResume.model_validate(profile.parsed_json)
    try:
        return agent.improve_profile(parsed)
    except Exception as exc:
        logger.exception("Profile improvement via LLM failed")
        raise HTTPException(status_code=502, detail=f"Profile improvement failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Jobs: search/aggregate, persist, list
# ---------------------------------------------------------------------------


@app.post("/jobs/search", response_model=list[JobSearchResultOut])
def search_jobs(request: JobSearchRequest, db: Session = Depends(get_db)) -> list[JobSearchResultOut]:
    try:
        source = SerpApiJobSource()
        listings = source.search(request.query, request.location, request.num_results)
    except JobSourceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    stored_jobs: list[Job] = []
    for listing in listings:
        existing = db.execute(select(Job).where(Job.external_id == listing.external_id)).scalar_one_or_none()
        if existing:
            stored_jobs.append(existing)
            continue
        job = Job(**listing.model_dump())
        db.add(job)
        stored_jobs.append(job)

    db.commit()
    for job in stored_jobs:
        db.refresh(job)

    words: set[str] = set()
    if request.profile_id:
        profile = db.get(Profile, request.profile_id)
        if profile:
            words = resume_tokens(profile.parsed_json)

    results = [
        JobSearchResultOut(
            **JobOut.model_validate(job).model_dump(),
            match_score=score_job(words, job.title, job.description) if words else None,
        )
        for job in stored_jobs
    ]
    if words:
        results.sort(key=lambda r: r.match_score or 0.0, reverse=True)
    return results


@app.post("/jobs/from-url", response_model=JobSearchResultOut)
def add_job_from_url(request: JobFromUrlRequest, db: Session = Depends(get_db)) -> JobSearchResultOut:
    """Lets a user paste an apply link they found themselves (outside our
    scraped search results) and pulls in enough of the page for gap analysis
    to run against it, same as any other job in the list."""
    external_id = hashlib.sha256(request.url.strip().lower().encode("utf-8")).hexdigest()
    job = db.execute(select(Job).where(Job.external_id == external_id)).scalar_one_or_none()

    if not job:
        try:
            fetched = fetch_job_from_url(request.url)
        except JobFetchError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        job = Job(
            external_id=external_id,
            title=fetched["title"],
            company="(from link)",
            location=None,
            description=fetched["description"],
            apply_url=request.url,
            source="user_provided_link",
        )
        db.add(job)
        db.commit()
        db.refresh(job)

    match_score = None
    if request.profile_id:
        profile = db.get(Profile, request.profile_id)
        if profile:
            words = resume_tokens(profile.parsed_json)
            match_score = score_job(words, job.title, job.description) if words else None

    return JobSearchResultOut(**JobOut.model_validate(job).model_dump(), match_score=match_score)


@app.get("/jobs", response_model=list[JobOut])
def list_jobs(db: Session = Depends(get_db), limit: int = 50) -> list[Job]:
    return list(db.execute(select(Job).order_by(Job.scraped_at.desc()).limit(limit)).scalars())


@app.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: uuid.UUID, db: Session = Depends(get_db)) -> Job:
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


# ---------------------------------------------------------------------------
# Gap analysis
# ---------------------------------------------------------------------------


@app.post("/gap-analysis", response_model=GapAnalysisOut)
def run_gap_analysis(request: GapAnalysisRequest, db: Session = Depends(get_db)) -> GapAnalysis:
    profile = db.get(Profile, request.profile_id)
    job = db.get(Job, request.job_id)
    if not profile or not job:
        raise HTTPException(status_code=404, detail="Profile or job not found.")

    existing = db.execute(
        select(GapAnalysis).where(
            GapAnalysis.profile_id == request.profile_id, GapAnalysis.job_id == request.job_id
        )
    ).scalar_one_or_none()
    if existing:
        return existing

    parsed = ParsedResume.model_validate(profile.parsed_json)
    try:
        result: GapAnalysisResult = agent.analyze_gap(parsed, job.title, job.description or "")
    except Exception as exc:
        logger.exception("Gap analysis via LLM failed")
        raise HTTPException(status_code=502, detail=f"Gap analysis failed: {exc}") from exc

    analysis = GapAnalysis(
        profile_id=request.profile_id,
        job_id=request.job_id,
        match_percentage=result.match_percentage,
        matching_skills=result.matching_skills,
        missing_requirements=result.missing_requirements,
        recommendations=[r.model_dump() for r in result.recommendations],
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return analysis


# ---------------------------------------------------------------------------
# Chat assistant
# ---------------------------------------------------------------------------


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    parsed = None
    if request.profile_id:
        profile = db.get(Profile, request.profile_id)
        if profile:
            parsed = ParsedResume.model_validate(profile.parsed_json)

    try:
        reply = agent.chat(
            request.message,
            [turn.model_dump() for turn in request.history],
            parsed,
        )
    except Exception as exc:
        logger.exception("Chat via LLM failed")
        raise HTTPException(status_code=502, detail=f"Chat failed: {exc}") from exc

    return ChatResponse(reply=reply)


# ---------------------------------------------------------------------------
# Applications: state tracking + pre-fill assistant trigger
# ---------------------------------------------------------------------------


@app.post("/applications", response_model=ApplicationOut)
def create_application(request: ApplicationCreate, db: Session = Depends(get_db)) -> Application:
    existing = db.execute(
        select(Application).where(Application.user_id == request.user_id, Application.job_id == request.job_id)
    ).scalar_one_or_none()
    if existing:
        return existing

    application = Application(user_id=request.user_id, job_id=request.job_id, notes=request.notes)
    db.add(application)
    db.commit()
    db.refresh(application)
    return application


@app.get("/applications", response_model=list[ApplicationOut])
def list_applications(user_id: uuid.UUID, db: Session = Depends(get_db)) -> list[Application]:
    return list(db.execute(select(Application).where(Application.user_id == user_id)).scalars())


@app.patch("/applications/{application_id}", response_model=ApplicationOut)
def update_application(
    application_id: uuid.UUID, request: ApplicationUpdate, db: Session = Depends(get_db)
) -> Application:
    application = db.get(Application, application_id)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found.")
    if request.status is not None:
        application.status = request.status
    if request.notes is not None:
        application.notes = request.notes
    db.commit()
    db.refresh(application)
    return application


@app.post("/applications/{application_id}/prefill")
def prefill(application_id: uuid.UUID, profile_data: PrefillRequest, db: Session = Depends(get_db)) -> dict:
    """Launches a visible browser and best-effort fills the application form.

    NOTE: this must run on a machine with a display attached (i.e. the user's
    own machine running this API locally) — it is not suitable for a headless
    server deployment. It never submits the form.
    """
    application = db.get(Application, application_id)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found.")
    job = db.get(Job, application.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Associated job not found.")

    profile_row = db.execute(select(Profile).where(Profile.user_id == application.user_id)).scalar_one_or_none()
    resume_file_path = profile_row.resume_file_path if profile_row else None

    applicant = ApplicantProfile(
        full_name=profile_data.full_name,
        email=profile_data.email,
        phone=profile_data.phone,
        linkedin_url=profile_data.linkedin_url,
        github_url=profile_data.github_url,
        resume_file_path=resume_file_path,
    )

    try:
        result = prefill_application(job.apply_url, applicant)
    except Exception as exc:
        logger.exception("Pre-fill assistant failed")
        raise HTTPException(status_code=500, detail=f"Pre-fill assistant failed: {exc}") from exc

    application.status = ApplicationStatus.prefilled
    db.commit()

    return {"filled_fields": result.filled_fields, "skipped_reason": result.skipped_reason}
