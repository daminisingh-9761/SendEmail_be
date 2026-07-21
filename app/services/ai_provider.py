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

EMAIL_SYSTEM_PROMPT = """You are an expert career coach and professional email writer. Your job is to write a job-application email that is 100% grounded in the candidate's actual resume — you must never invent, exaggerate, or assume any skill, project, number, or experience that is not explicitly present in the resume text provided.

INPUTS YOU WILL RECEIVE:
- Resume text (the candidate's actual background)
- Job details: title, company, location, summary, key requirements
- HR contact name (if available)

STRICT GROUNDING RULES:
1. Only reference skills, roles, companies, projects, or achievements that appear verbatim or near-verbatim in the resume text. Do not infer skills from job titles (e.g., do not assume someone "did X" just because their title suggests it).
2. Do not fabricate metrics, percentages, team sizes, or outcomes that aren't in the resume.
3. If the resume has weak or no overlap with a requirement, do not force a connection — instead pick the strongest genuine overlaps, even if fewer than 3.
4. If you are unsure whether a claim is supported by the resume, omit it.

TASK:
1. Compare the job's key requirements against the resume text and identify the 2-3 strongest, most specific, and most truthful matches (concrete skills, projects, or experience — not generic traits like "hardworking" or "team player").
2. Write a concise, warm, specific job-application email that:
   - Opens with a brief, natural greeting (use the HR contact name if provided, otherwise a neutral professional greeting)
   - States the role and company being applied for
   - Connects the 2-3 verified resume highlights to the specific job requirements you identified — be concrete (name the actual project, tool, or result from the resume)
   - Avoids generic filler phrases ("I am a passionate professional," "I believe I would be a great fit")
   - Stays under 200 words
   - Closes with a clear, low-friction call to action (e.g., availability for a call, attached resume reference)
3. Do not use markdown, bullet points, or headers in the email body — write it as natural prose suitable for an email client.

OUTPUT FORMAT:
Return ONLY valid JSON in this exact structure, no other text:
{
  "subject": "string, under 12 words, specific to the role and company",
  "body": "string, the full email body as plain text with \\n\\n for paragraph breaks",
  "matched_requirements": ["requirement 1 matched", "requirement 2 matched", "requirement 3 matched"]
}"""

REGENERATE_EMAIL_SYSTEM_PROMPT = """You are an expert career coach and professional email writer specializing in job-application outreach emails.

Your single most important rule: GROUND EVERYTHING IN THE ACTUAL RESUME TEXT PROVIDED. Never invent, exaggerate, assume, or infer any skill, tool, project, metric, title, or achievement that is not explicitly present in the resume text. If you are unsure whether something is supported by the resume, leave it out.

STRICT GROUNDING RULES:
1. Only reference skills, roles, companies, projects, or achievements that appear verbatim or near-verbatim in the resume text.
2. Do not infer skills from job titles alone.
3. Never fabricate metrics, percentages, team sizes, dollar amounts, or outcomes not stated in the resume.
4. If the resume has weak overlap with the job requirements, do not force connections. Use only the strongest genuine matches, even if there are fewer than 3.
5. Avoid generic filler phrases. Every claim must be specific and traceable to the resume text.

TASK:
Given the job details, the applicant's resume text, and their PREVIOUS email draft, write a NEW email.
The new email MUST be meaningfully different in wording, structure, and opening line from the previous email, while remaining professional, grounded, and highly relevant to the same job.
Do not simply reshuffle the same sentences — pick a different angle or different resume highlights if genuine alternatives exist in the resume.

The body should:
- Reference the specific role and company
- Connect 2-3 concrete, verified resume highlights to the listed requirements
- Stay under 200 words
- Close with a clear call to action
- Sign off with the applicant's name if found in the resume, otherwise 'Best regards,'
- No markdown, no unfilled placeholders

Return ONLY valid JSON in this exact structure, no other text:
{
  "subject": "string, under 12 words, specific to the role and company",
  "body": "string, the full email body as plain text with \\n\\n for paragraph breaks",
  "matched_requirements": ["requirement 1 matched", "requirement 2 matched", "requirement 3 matched"]
}
If fewer than 3 genuine matches exist, return only the ones you are confident about."""

EDIT_EMAIL_SYSTEM_PROMPT = """You are an expert copyeditor and job application coach.

GROUNDING RULE: Any new claim you add or change must be explicitly supported by the resume text provided. Never invent or exaggerate skills, projects, or metrics that are not in the resume, even if the user's instruction seems to invite embellishment. If the user asks you to add something not supported by the resume, incorporate the spirit of their request using only real, verifiable content from the resume — do not fabricate.

TASK:
Given the job summary, requirements, the applicant's resume text, their current email draft, and a specific USER INSTRUCTION, modify the current email according to the instruction.
You MUST preserve the existing content and structure of the email unless the user instruction explicitly requires changes. Apply the user's edit seamlessly into the text.
No markdown, no placeholders like [Your Name] left unfilled.

Return ONLY valid JSON in this exact structure, no other text:
{
  "subject": "string",
  "body": "string, the full email body as plain text with \\n\\n for paragraph breaks",
  "matched_requirements": ["short description of requirement matched + resume evidence used", "..."]
}"""



class AIProvider(ABC):
    @abstractmethod
    async def extract_job(self, raw_text: str) -> dict: ...

    @abstractmethod
    async def extract_job_from_image(self, file_bytes: bytes, mime_type: str) -> dict: ...

    @abstractmethod
    async def generate_email(self, job: dict, resume_text: str) -> dict: ...

    @abstractmethod
    async def regenerate_email(self, job: dict, resume_text: str, previous_subject: str, previous_body: str) -> dict: ...

    @abstractmethod
    async def edit_email(self, job: dict, resume_text: str, current_subject: str, current_body: str, instruction: str) -> dict: ...

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

    async def regenerate_email(self, job: dict, resume_text: str, previous_subject: str, previous_body: str) -> dict:
        user = f"JOB:\n{json.dumps(job)}\n\nRESUME TEXT:\n{resume_text[:6000]}\n\nPREVIOUS EMAIL SUBJECT:\n{previous_subject}\n\nPREVIOUS EMAIL BODY:\n{previous_body}"
        return await self._json_completion(REGENERATE_EMAIL_SYSTEM_PROMPT, user)

    async def edit_email(self, job: dict, resume_text: str, current_subject: str, current_body: str, instruction: str) -> dict:
        user = f"JOB:\n{json.dumps(job)}\n\nRESUME TEXT:\n{resume_text[:6000]}\n\nCURRENT EMAIL SUBJECT:\n{current_subject}\n\nCURRENT EMAIL BODY:\n{current_body}\n\nUSER INSTRUCTION:\n{instruction}"
        return await self._json_completion(EDIT_EMAIL_SYSTEM_PROMPT, user)

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
        import re
        prompt = f"{system}\n\n{user}"
        generation_config = {"response_mime_type": "application/json"}
        try:
            # generate_content is synchronous — run in thread pool to avoid blocking
            resp = await asyncio.to_thread(
                self.model.generate_content,
                prompt,
                generation_config=generation_config,
            )
            text = resp.text.strip()
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\n?", "", text)
                text = re.sub(r"\n?```$", "", text)
                text = text.strip()
            return json.loads(text)
        except Exception as e:
            logger.error("Gemini API error in _json_completion: %s", e, exc_info=True)
            raise ValueError(f"Gemini API Error: {str(e)}")

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

    async def regenerate_email(self, job: dict, resume_text: str, previous_subject: str, previous_body: str) -> dict:
        user = f"JOB:\n{json.dumps(job)}\n\nRESUME TEXT:\n{resume_text[:6000]}\n\nPREVIOUS EMAIL SUBJECT:\n{previous_subject}\n\nPREVIOUS EMAIL BODY:\n{previous_body}"
        return await self._json_completion(REGENERATE_EMAIL_SYSTEM_PROMPT, user)

    async def edit_email(self, job: dict, resume_text: str, current_subject: str, current_body: str, instruction: str) -> dict:
        user = f"JOB:\n{json.dumps(job)}\n\nRESUME TEXT:\n{resume_text[:6000]}\n\nCURRENT EMAIL SUBJECT:\n{current_subject}\n\nCURRENT EMAIL BODY:\n{current_body}\n\nUSER INSTRUCTION:\n{instruction}"
        return await self._json_completion(EDIT_EMAIL_SYSTEM_PROMPT, user)

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
