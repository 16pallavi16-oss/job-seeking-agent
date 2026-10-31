"""Best-effort extraction of a job title/description from an arbitrary apply
link the user found themselves (not one of our scraped SerpApi listings).

Job sites vary wildly in structure (Greenhouse, Lever, Workday, LinkedIn,
plain company pages...), so this doesn't try to parse any specific site's
markup — it just pulls the page's title/og:title and its visible text, which
is enough signal for the LLM-driven gap analysis downstream.
"""

import re

import requests
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (compatible; JobSeekerBot/1.0)"
DESCRIPTION_CHAR_LIMIT = 6000


class JobFetchError(Exception):
    pass


def fetch_job_from_url(url: str) -> dict:
    try:
        response = requests.get(url, timeout=15, headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
    except requests.RequestException as exc:
        raise JobFetchError(f"Could not fetch that URL: {exc}") from exc

    soup = BeautifulSoup(response.text, "html.parser")

    title = None
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = og_title["content"].strip()
    elif soup.title and soup.title.string:
        title = soup.title.string.strip()

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(separator=" ")).strip()
    if not text:
        raise JobFetchError("That page has no readable text to analyze.")

    return {
        "title": title or "Job posting",
        "description": text[:DESCRIPTION_CHAR_LIMIT],
    }
