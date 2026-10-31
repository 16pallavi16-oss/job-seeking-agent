"""Resume-to-job relevance scoring — a dependency-free stand-in for real
semantic search. Scores how much of the resume's own vocabulary (skills,
past titles, summary) shows up in a job's title/description, so search
results can be ranked by fit to the candidate rather than left in whatever
order the job source returned them.
"""

import re

_STOPWORDS = {
    "the", "and", "a", "an", "to", "of", "in", "for", "with", "on", "at",
    "by", "is", "are", "this", "that", "or", "as", "be", "will", "we",
}
_TOKEN_RE = re.compile(r"[a-z0-9+.#]+")


def _tokenize(text: str) -> set[str]:
    words = (w.rstrip(".") for w in _TOKEN_RE.findall(text.lower()))
    return {w for w in words if w not in _STOPWORDS and len(w) > 1}


def resume_tokens(parsed_resume: dict) -> set[str]:
    parts: list[str] = list(parsed_resume.get("skills") or [])
    for exp in parsed_resume.get("experience") or []:
        if exp.get("title"):
            parts.append(exp["title"])
    if parsed_resume.get("summary"):
        parts.append(parsed_resume["summary"])
    return _tokenize(" ".join(parts))


def score_job(resume_words: set[str], job_title: str, job_description: str | None) -> float:
    """Fraction of the resume's vocabulary that also appears in the job posting."""
    if not resume_words:
        return 0.0
    job_words = _tokenize(f"{job_title} {job_description or ''}")
    if not job_words:
        return 0.0
    overlap = resume_words & job_words
    return round(len(overlap) / len(resume_words), 3)
