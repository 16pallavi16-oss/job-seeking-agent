import io

import pdfplumber


class ResumeParsingError(Exception):
    pass


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract raw text from a PDF resume. Raises ResumeParsingError on empty/corrupt files."""
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            pages_text = [page.extract_text() or "" for page in pdf.pages]
    except Exception as exc:
        raise ResumeParsingError(f"Could not read PDF: {exc}") from exc

    text = "\n".join(pages_text).strip()
    if not text:
        raise ResumeParsingError("No extractable text found in PDF (it may be a scanned image).")
    return text
