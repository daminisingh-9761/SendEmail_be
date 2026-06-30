"""Turns raw job input (text / file / URL) into a structured job record.

For files: PDFs are parsed with pypdf; images go through OCR (pytesseract).
For URLs: the page is fetched and the main content is isolated with BeautifulSoup.
The cleaned text is then handed to the AI provider to extract structured fields
and (separately) to look for a hiring contact's email address.
"""
import re
import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader
from PIL import Image
import pytesseract
import io

from app.services.ai_provider import get_ai_provider

EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
GENERIC_LOCAL_PARTS = {"noreply", "no-reply", "support", "info", "privacy", "unsubscribe"}


async def text_from_url(url: str) -> str:
    async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
        resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; MailjobBot/1.0)"})
        resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def text_from_pdf(file_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(file_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def text_from_image(file_bytes: bytes) -> str:
    image = Image.open(io.BytesIO(file_bytes))
    return pytesseract.image_to_string(image)


def find_candidate_emails(raw_text: str) -> list[str]:
    """Heuristic pass before the AI pass: prefer emails near words like
    'hr', 'careers', 'recruit', 'apply', and de-prioritize generic mailboxes."""
    found = EMAIL_RE.findall(raw_text)
    scored = []
    lowered = raw_text.lower()
    for email in set(found):
        local_part = email.split("@")[0].lower()
        if local_part in GENERIC_LOCAL_PARTS:
            continue
        idx = lowered.find(email.lower())
        window = lowered[max(0, idx - 60): idx + 60]
        score = sum(kw in window for kw in ["hr", "careers", "recruit", "talent", "apply", "hiring"])
        scored.append((score, email))
    scored.sort(key=lambda x: -x[0])
    return [e for _, e in scored]


async def extract_job_details(raw_text: str, source_type: str, source_raw: str) -> dict:
    ai = get_ai_provider()
    structured = await ai.extract_job(raw_text)

    candidate_emails = find_candidate_emails(raw_text)
    hr_email = structured.get("hrEmail") or (candidate_emails[0] if candidate_emails else None)

    return {
        "jobTitle": structured.get("jobTitle", "Untitled role"),
        "company": structured.get("company", "Unknown company"),
        "location": structured.get("location"),
        "hrEmail": hr_email,
        "hrName": structured.get("hrName"),
        "summary": structured.get("summary", ""),
        "keyRequirements": structured.get("keyRequirements", []),
        "sourceType": source_type,
        "sourceRaw": source_raw,
    }
