"""Semi-automated 'One-Click Pre-fill Browser Assistant'.

Fully automating job applications is brittle (ATS platforms change DOM
structure constantly) and risky (CAPTCHAs, ToS). Instead this launches a
real, visible Chromium window, best-effort fills the handful of fields that
are near-universal across ATS platforms (name, email, phone, LinkedIn,
GitHub, resume upload), and then stops — a human reviews every field and
clicks Submit themselves.

Must be run somewhere with a display (the user's own machine), since the
browser window is meant to be seen and interacted with.
"""

import logging
from dataclasses import dataclass, field

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright

logger = logging.getLogger(__name__)


@dataclass
class ApplicantProfile:
    full_name: str
    email: str
    phone: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    resume_file_path: str | None = None


@dataclass
class PrefillResult:
    filled_fields: list[str] = field(default_factory=list)
    skipped_reason: str | None = None


# Each entry: (profile attribute, keywords to match against name/id/placeholder/aria-label/label text)
_FIELD_KEYWORDS: list[tuple[str, list[str]]] = [
    ("full_name", ["full name", "fullname", "your name", "candidate name", "applicant name"]),
    ("email", ["email", "e-mail"]),
    ("phone", ["phone", "mobile", "contact number"]),
    ("linkedin_url", ["linkedin"]),
    ("github_url", ["github"]),
]

_NAME_SPLIT_KEYWORDS = {
    "first_name": ["first name", "firstname", "given name"],
    "last_name": ["last name", "lastname", "surname", "family name"],
}

_RESUME_KEYWORDS = ["resume", "cv", "curriculum vitae"]


_SIGNATURE_JS = (
    "el => [el.name, el.id, el.placeholder, el.getAttribute('aria-label'), "
    "document.querySelector('label[for=\"' + el.id + '\"]')?.innerText]"
    ".filter(Boolean).join(' ')"
)


def _element_signature(locator) -> str:
    """Concatenate the attributes/label text most likely to reveal a field's purpose."""
    try:
        attrs = locator.evaluate(_SIGNATURE_JS)
        return (attrs or "").lower()
    except Exception:
        return ""


def _matches_any(signature: str, keywords: list[str]) -> bool:
    return any(keyword in signature for keyword in keywords)


def prefill_application(apply_url: str, profile: ApplicantProfile, headless: bool = False) -> PrefillResult:
    result = PrefillResult()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        page = browser.new_page()

        try:
            page.goto(apply_url, wait_until="domcontentloaded", timeout=30000)
        except PlaywrightTimeoutError:
            logger.warning("Page load timed out for %s; continuing with best-effort fill.", apply_url)

        # Best-effort: give client-side rendered ATS forms (Greenhouse, Lever, Workday) a moment to mount.
        page.wait_for_timeout(2000)

        text_inputs = page.locator("input[type='text'], input[type='email'], input[type='tel'], input:not([type])")
        count = min(text_inputs.count(), 200)  # guard against pathological pages

        first_name_val, last_name_val = _split_name(profile.full_name)

        for i in range(count):
            locator = text_inputs.nth(i)
            try:
                if not locator.is_visible():
                    continue
            except Exception:
                continue

            signature = _element_signature(locator)
            if not signature:
                continue

            if _matches_any(signature, _NAME_SPLIT_KEYWORDS["first_name"]):
                _safe_fill(locator, first_name_val, "first_name", result)
                continue
            if _matches_any(signature, _NAME_SPLIT_KEYWORDS["last_name"]):
                _safe_fill(locator, last_name_val, "last_name", result)
                continue

            for attr_name, keywords in _FIELD_KEYWORDS:
                if _matches_any(signature, keywords):
                    value = getattr(profile, attr_name)
                    if value:
                        _safe_fill(locator, value, attr_name, result)
                    break

        if profile.resume_file_path:
            _fill_resume_upload(page, profile.resume_file_path, result)

        if not result.filled_fields:
            result.skipped_reason = (
                "No recognizable fields were found on this page — the ATS may use a custom "
                "widget (e.g. a multi-step wizard) or the form may be behind a login wall. "
                "Please fill it in manually."
            )

        # Intentionally left open for human review — never call browser.close() or submit anything here.
        logger.info("Pre-fill complete for %s. Filled: %s", apply_url, result.filled_fields)

    return result


def _split_name(full_name: str) -> tuple[str, str]:
    parts = full_name.strip().split()
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def _safe_fill(locator, value: str, field_name: str, result: PrefillResult) -> None:
    try:
        locator.fill(value)
        result.filled_fields.append(field_name)
    except Exception as exc:
        logger.debug("Could not fill field '%s': %s", field_name, exc)


def _fill_resume_upload(page: Page, resume_file_path: str, result: PrefillResult) -> None:
    file_inputs = page.locator("input[type='file']")
    for i in range(file_inputs.count()):
        locator = file_inputs.nth(i)
        signature = _element_signature(locator)
        if _matches_any(signature, _RESUME_KEYWORDS) or file_inputs.count() == 1:
            try:
                locator.set_input_files(resume_file_path)
                result.filled_fields.append("resume_upload")
                return
            except Exception as exc:
                logger.debug("Could not upload resume: %s", exc)
