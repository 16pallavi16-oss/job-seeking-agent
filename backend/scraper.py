"""Job aggregation via the SerpApi Google Jobs engine.

Google Jobs itself aggregates listings from LinkedIn, Indeed, Glassdoor, and
individual company ATS boards (Greenhouse, Lever, Workday, etc.) — spanning
both large MNCs and startups — and, critically, resolves each listing down to
the employer's *actual* apply link via `apply_options`. This avoids scraping
LinkedIn/Indeed directly, which their terms of service prohibit and which
aggressively CAPTCHA-gates automated/headless traffic.
"""

import hashlib
import logging

import requests
from pydantic import BaseModel

from backend.config import settings

logger = logging.getLogger(__name__)

SERPAPI_ENDPOINT = "https://serpapi.com/search"


class JobListing(BaseModel):
    external_id: str
    title: str
    company: str
    location: str | None = None
    description: str | None = None
    apply_url: str
    source: str = "serpapi_google_jobs"
    job_type: str | None = None


class JobSourceError(Exception):
    pass


def _make_external_id(title: str, company: str, apply_url: str) -> str:
    raw = f"{title.strip().lower()}|{company.strip().lower()}|{apply_url.strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _extract_apply_url(job: dict) -> str | None:
    apply_options = job.get("apply_options") or []
    if apply_options:
        return apply_options[0].get("link")
    related_links = job.get("related_links") or []
    if related_links:
        return related_links[0].get("link")
    return job.get("share_link")


def _extract_job_type(job: dict) -> str | None:
    for extension in job.get("detected_extensions", {}).values():
        if isinstance(extension, str) and any(
            keyword in extension.lower() for keyword in ("intern", "full-time", "part-time", "contract")
        ):
            return extension
    return job.get("detected_extensions", {}).get("schedule_type")


class SerpApiJobSource:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or settings.SERPAPI_API_KEY
        if not self.api_key:
            raise JobSourceError("SERPAPI_API_KEY is not configured.")

    def search(self, query: str, location: str | None = None, num_results: int = 20) -> list[JobListing]:
        params = {
            "engine": "google_jobs",
            "q": query,
            "api_key": self.api_key,
            "hl": "en",
        }
        if location:
            params["location"] = location

        listings: list[JobListing] = []
        next_page_token: str | None = None

        while len(listings) < num_results:
            if next_page_token:
                params["next_page_token"] = next_page_token

            try:
                response = requests.get(SERPAPI_ENDPOINT, params=params, timeout=20)
                response.raise_for_status()
            except requests.RequestException as exc:
                raise JobSourceError(f"SerpApi request failed: {exc}") from exc

            data = response.json()
            jobs_results = data.get("jobs_results", [])
            if not jobs_results:
                break

            for job in jobs_results:
                apply_url = _extract_apply_url(job)
                if not apply_url:
                    continue  # skip listings with no resolvable apply link
                title = job.get("title", "")
                company = job.get("company_name", "")
                listings.append(
                    JobListing(
                        external_id=_make_external_id(title, company, apply_url),
                        title=title,
                        company=company,
                        location=job.get("location"),
                        description=job.get("description"),
                        apply_url=apply_url,
                        job_type=_extract_job_type(job),
                    )
                )
                if len(listings) >= num_results:
                    break

            next_page_token = data.get("serpapi_pagination", {}).get("next_page_token")
            if not next_page_token:
                break

        return listings[:num_results]
