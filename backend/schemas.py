import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from backend.models import ApplicationStatus


class JobSearchRequest(BaseModel):
    query: str
    location: str | None = None
    num_results: int = 20
    profile_id: uuid.UUID | None = None


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    company: str
    location: str | None
    description: str | None
    apply_url: str
    source: str
    job_type: str | None
    posted_at: datetime | None


class JobSearchResultOut(JobOut):
    match_score: float | None = None


class JobFromUrlRequest(BaseModel):
    url: str
    profile_id: uuid.UUID | None = None


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []
    profile_id: uuid.UUID | None = None


class ChatResponse(BaseModel):
    reply: str


class AddSkillsRequest(BaseModel):
    skills: list[str]


class GapAnalysisRequest(BaseModel):
    profile_id: uuid.UUID
    job_id: uuid.UUID


class GapAnalysisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    profile_id: uuid.UUID
    job_id: uuid.UUID
    match_percentage: int
    matching_skills: list[str]
    missing_requirements: list[str]
    recommendations: list[dict]
    created_at: datetime


class ApplicationCreate(BaseModel):
    user_id: uuid.UUID
    job_id: uuid.UUID
    notes: str | None = None


class ApplicationUpdate(BaseModel):
    status: ApplicationStatus | None = None
    notes: str | None = None


class ApplicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    job_id: uuid.UUID
    status: ApplicationStatus
    notes: str | None
    applied_at: datetime | None
    created_at: datetime


class PrefillRequest(BaseModel):
    full_name: str
    email: str
    phone: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
