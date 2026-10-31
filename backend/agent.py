"""LangChain + Groq agent logic: resume parsing, profile improvement, and
job-gap analysis. Every LLM call is bound to a Pydantic schema via
`with_structured_output`, so the model's response either validates or raises
— callers never have to hand-parse LLM text.
"""

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field

from backend.config import settings


# ---------------------------------------------------------------------------
# Structured output schemas — these double as the LLM's tool-call schema
# (LangChain's with_structured_output) and as the shape persisted to Postgres.
# ---------------------------------------------------------------------------


class Experience(BaseModel):
    company: str
    title: str
    duration: str = Field(description="e.g. 'Jan 2023 - Present' or '6 months'")
    highlights: list[str] = Field(default_factory=list, description="Bullet points of impact/responsibilities")


class Education(BaseModel):
    institution: str
    degree: str
    field_of_study: str | None = None
    graduation_year: str | None = None


class ContactInfo(BaseModel):
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    portfolio_url: str | None = None


class ParsedResume(BaseModel):
    contact_info: ContactInfo
    summary: str | None = Field(default=None, description="Professional summary / objective, if present")
    skills: list[str] = Field(default_factory=list, description="Flat list of technical and soft skills")
    experience: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)


class ProfileImprovement(BaseModel):
    missing_keywords: list[str] = Field(
        description="Industry-standard keywords/skills that are absent but expected for this candidate's apparent target roles"
    )
    formatting_issues: list[str] = Field(
        description="Concrete formatting/structure problems (e.g. no quantified impact, inconsistent dates)"
    )
    suggestions: list[str] = Field(
        description="Actionable, specific rewrite suggestions the candidate can apply immediately"
    )
    overall_assessment: str = Field(description="2-3 sentence summary of resume strength")


class RecommendationItem(BaseModel):
    gap: str = Field(description="The missing skill/requirement this recommendation addresses")
    action: str = Field(
        description="A concrete, time-boxed action, e.g. 'Build a 3-day project doing X' or 'Take free course Y (link/name)'"
    )


class GapAnalysisResult(BaseModel):
    match_percentage: int = Field(ge=0, le=100)
    matching_skills: list[str]
    missing_requirements: list[str]
    recommendations: list[RecommendationItem]


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class JobSeekerAgent:
    def __init__(self, model: str | None = None) -> None:
        self._model = model
        self._llm_instance: ChatGroq | None = None

    @property
    def _llm(self) -> ChatGroq:
        # Built lazily, on first actual LLM call, so the app can start (and
        # non-LLM endpoints work) even before GROQ_API_KEY is configured.
        if self._llm_instance is None:
            self._llm_instance = ChatGroq(
                model=self._model or settings.GROQ_MODEL,
                api_key=settings.GROQ_API_KEY,
                max_tokens=4096,
            )
        return self._llm_instance

    def parse_resume(self, resume_text: str) -> ParsedResume:
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You extract structured data from resumes. Extract only what is explicitly "
                    "present in the text — never invent skills, dates, or companies. If a field "
                    "isn't present, omit it or leave the list empty.",
                ),
                ("human", "Resume text:\n\n{resume_text}"),
            ]
        )
        chain = prompt | self._llm.with_structured_output(ParsedResume)
        return chain.invoke({"resume_text": resume_text})

    def improve_profile(self, parsed_resume: ParsedResume) -> ProfileImprovement:
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a career coach reviewing a resume standalone (no specific job in mind). "
                    "Identify missing industry-standard keywords for the candidate's apparent field, "
                    "concrete formatting/structure weaknesses, and specific actionable rewrite suggestions. "
                    "Be concrete — reference the candidate's actual experience, not generic advice.",
                ),
                ("human", "Parsed resume JSON:\n\n{resume_json}"),
            ]
        )
        chain = prompt | self._llm.with_structured_output(ProfileImprovement)
        return chain.invoke({"resume_json": parsed_resume.model_dump_json(indent=2)})

    def analyze_gap(self, parsed_resume: ParsedResume, job_title: str, job_description: str) -> GapAnalysisResult:
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You compare a candidate's resume against a specific job description and produce "
                    "an honest, actionable gap analysis. match_percentage should reflect genuine overlap "
                    "in required skills/experience, not optimism. For every missing requirement, give a "
                    "recommendation that is small and concrete enough to start today — e.g. 'Build a 3-day "
                    "project doing X' or 'Take free course Y' — never vague advice like 'gain more experience'.",
                ),
                (
                    "human",
                    "Candidate resume JSON:\n\n{resume_json}\n\n"
                    "Job title: {job_title}\n\nJob description:\n\n{job_description}",
                ),
            ]
        )
        chain = prompt | self._llm.with_structured_output(GapAnalysisResult)
        return chain.invoke(
            {
                "resume_json": parsed_resume.model_dump_json(indent=2),
                "job_title": job_title,
                "job_description": job_description,
            }
        )

    def chat(self, message: str, history: list[dict], parsed_resume: ParsedResume | None = None) -> str:
        system_text = (
            "You are a direct, practical career assistant embedded in a job-seeker app. "
            "Answer questions about the candidate's resume, skill gaps, and job search strategy. "
            "Point out anything obviously missing from their resume when relevant. Be specific — "
            "reference their actual resume content rather than giving generic advice. Keep answers concise."
        )
        if parsed_resume:
            system_text += f"\n\nCandidate's parsed resume (JSON):\n{parsed_resume.model_dump_json(indent=2)}"
        else:
            system_text += "\n\nThe candidate hasn't uploaded a resume yet — you may not have that context."

        messages: list[BaseMessage] = [SystemMessage(content=system_text)]
        for turn in history:
            if turn.get("role") == "user":
                messages.append(HumanMessage(content=turn["content"]))
            else:
                messages.append(AIMessage(content=turn["content"]))
        messages.append(HumanMessage(content=message))

        response = self._llm.invoke(messages)
        return response.content


agent = JobSeekerAgent()
