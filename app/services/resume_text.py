"""Extracts plain text from a stored resume file so it can be fed to the AI
email-writing prompt. PDF only for brevity here; extend for DOCX with
python-docx if needed."""
from pypdf import PdfReader


def extract_resume_text(storage_path: str) -> str:
    if storage_path.lower().endswith(".pdf"):
        reader = PdfReader(storage_path)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    with open(storage_path, "r", errors="ignore") as f:
        return f.read()
