"""Thin abstraction over OpenAI / Gemini so the rest of the app doesn't care
which model is configured. Both providers are asked to return strict JSON.
"""
import json
import asyncio
import logging
from abc import ABC, abstractmethod
from app.core.config import get_settings

logger = logging.getLogger(__name__)

EXTRACT_SYSTEM_PROMPT = """You are a job-post parser. Given raw scraped or OCR'd text
from a job listing, return ONLY valid JSON (no markdown fences) with keys:
jobTitle, company, location, hrEmail, hrName, summary (2-3 sentences),
keyRequirements (array of up to 6 short strings).
If a field isn't present, use null (or [] for keyRequirements). Never invent an email
address that does not literally appear in the text."""

EMAIL_SYSTEM_PROMPT = """You write concise, warm, specific job-application emails.
Given a job summary, requirements, the applicant's resume text, and the hiring
contact's name (if known), write a JSON object with keys "subject" and "body".
The body should: reference the specific role and company, connect 2-3 concrete
resume highlights to the listed requirements, stay under 200 words, and close
with a clear call to action. Sign off with the applicant's name. No markdown,
no placeholders like [Your Name] left unfilled — use the actual resume name if found,
otherwise sign 'Best regards,' with no name."""


class AIProvider(ABC):
    @abstractmethod
    async def extract_job(self, raw_text: str) -> dict: ...

    @abstractmethod
    async def extract_job_from_image(self, file_bytes: bytes, mime_type: str) -> dict: ...

    @abstractmethod
    async def generate_email(self, job: dict, resume_text: str) -> dict: ...

    @abstractmethod
    async def generate_follow_up(self, job: dict, original_body: str) -> str: ...


class OpenAIProvider(AIProvider):
    def __init__(self):
        from openai import AsyncOpenAI
        settings = get_settings()
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model

    async def _json_completion(self, system: str, user: str) -> dict:
        resp = await self.client.chat.completions.create(
            model=self.model,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.4,
        )
        return json.loads(resp.choices[0].message.content)

    async def extract_job(self, raw_text: str) -> dict:
        return await self._json_completion(EXTRACT_SYSTEM_PROMPT, raw_text[:12000])

    async def extract_job_from_image(self, file_bytes: bytes, mime_type: str) -> dict:
        import base64
        base64_image = base64.b64encode(file_bytes).decode('utf-8')
        resp = await self.client.chat.completions.create(
            model=self.model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": EXTRACT_SYSTEM_PROMPT},
                {"role": "user", "content": [
                    {"type": "text", "text": "Extract job details from this image."},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{base64_image}"}}
                ]}
            ],
            temperature=0.4,
        )
        return json.loads(resp.choices[0].message.content)

    async def generate_email(self, job: dict, resume_text: str) -> dict:
        user = f"JOB:\n{json.dumps(job)}\n\nRESUME TEXT:\n{resume_text[:6000]}"
        return await self._json_completion(EMAIL_SYSTEM_PROMPT, user)

    async def generate_follow_up(self, job: dict, original_body: str) -> str:
        system = "Write a brief, polite follow-up email (under 100 words) referencing the original application. Return plain text only."
        user = f"JOB: {json.dumps(job)}\nORIGINAL EMAIL:\n{original_body}"
        resp = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.5,
        )
        return resp.choices[0].message.content.strip()


class GeminiProvider(AIProvider):
    def __init__(self):
        import google.generativeai as genai
        settings = get_settings()
        print("AI Provider:", settings.ai_provider)
        print("Gemini Model:", settings.gemini_model)
        print("Gemini Key:", settings.gemini_api_key[:20])
        genai.configure(api_key=settings.gemini_api_key)
        self.model = genai.GenerativeModel(settings.gemini_model)

    async def _json_completion(self, system: str, user: str) -> dict:
        prompt = f"{system}\n\n{user}"
        generation_config = {"response_mime_type": "application/json"}
        try:
            # generate_content is synchronous — run in thread pool to avoid blocking
            resp = await asyncio.to_thread(
                self.model.generate_content,
                prompt,
                generation_config=generation_config,
            )
            return json.loads(resp.text)
        except Exception as e:
            logger.error("Gemini API error in _json_completion: %s", e, exc_info=True)
            raise

    async def extract_job(self, raw_text: str) -> dict:
        return await self._json_completion(EXTRACT_SYSTEM_PROMPT, raw_text[:12000])

    async def extract_job_from_image(self, file_bytes: bytes, mime_type: str) -> dict:
        part = {
            "mime_type": mime_type,
            "data": file_bytes
        }
        resp = self.model.generate_content(
            [EXTRACT_SYSTEM_PROMPT, part],
            generation_config={"response_mime_type": "application/json"},
        )
        return json.loads(resp.text)

    async def generate_email(self, job: dict, resume_text: str) -> dict:
        user = f"JOB:\n{json.dumps(job)}\n\nRESUME TEXT:\n{resume_text[:6000]}"
        return await self._json_completion(EMAIL_SYSTEM_PROMPT, user)

    async def generate_follow_up(self, job: dict, original_body: str) -> str:
        prompt = (
            "Write a brief, polite follow-up email (under 100 words) referencing the "
            f"original application. Plain text only.\nJOB: {json.dumps(job)}\nORIGINAL EMAIL:\n{original_body}"
        )
        resp = self.model.generate_content(prompt)
        return resp.text.strip()


def get_ai_provider() -> AIProvider:
    settings = get_settings()
    if settings.ai_provider == "gemini":
        return GeminiProvider()
    return OpenAIProvider()
