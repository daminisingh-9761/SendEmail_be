from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
import uuid
from datetime import datetime

from app.db.session import get_db
from app.schemas.job import ExtractedJobOut, GenerateEmailRequest, GeneratedEmailOut, JobExtractTextRequest
from app.api.deps import get_current_user
from app.services import job_extraction
from app.services.ai_provider import get_ai_provider
from app.services.resume_text import extract_resume_text

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/extract", response_model=ExtractedJobOut)
async def extract_job(
    payload: JobExtractTextRequest,
    user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    if payload.type == "url":
        if not payload.url:
            raise HTTPException(400, "url is required")
        raw_text = await job_extraction.text_from_url(payload.url)
        source_raw = payload.url
    else:
        if not payload.text:
            raise HTTPException(400, "text is required")
        raw_text = payload.text
        source_raw = payload.text

    details = await job_extraction.extract_job_details(raw_text, payload.type, source_raw)
    application = await _create_draft_application(db, user, details)
    return _to_extracted_job_out(application)


@router.post("/extract-file", response_model=ExtractedJobOut)
async def extract_job_file(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    contents = await file.read()
    if file.content_type == "application/pdf":
        raw_text = job_extraction.text_from_pdf(contents)
        details = await job_extraction.extract_job_details(raw_text, "file", file.filename)
    elif file.content_type.startswith("image/"):
        details = await job_extraction.extract_job_details_from_image(contents, file.content_type, "file", file.filename)
    else:
        raise HTTPException(400, "Unsupported file type. Only PDF and image files are supported.")
    application = await _create_draft_application(db, user, details)
    return _to_extracted_job_out(application)


@router.post("/generate-email", response_model=GeneratedEmailOut)
async def generate_email(
    payload: GenerateEmailRequest,
    user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    import logging
    logger = logging.getLogger(__name__)
    logger.info("===== generate_email endpoint called =====")
    application = await db.applications.find_one({"id": payload.jobId})
    if application is None or application["user_id"] != user["id"]:
        raise HTTPException(404, "Application not found")

    resume = await db.resumes.find_one({"user_id": user["id"], "is_default": True})
    if resume is None:
        raise HTTPException(400, "Please upload a resume first to generate an email.")

    try:
        resume_text = extract_resume_text(resume["storage_path"])
    except Exception as e:
        logger.error("Failed to extract resume text: %s", e)
        raise HTTPException(400, "The associated resume file is missing or inaccessible. Please upload a new resume and try again.")

    ai = get_ai_provider()
    logger.info("AI provider created")
    job_dict = {
        "jobTitle": application["job_title"],
        "company": application["company"],
        "location": application.get("location"),
        "summary": application["job_summary"],
        "keyRequirements": application["key_requirements"],
    }
    logger.info("Calling AI provider to generate email...")
    try:
        email = await ai.generate_email(job_dict, resume_text)
    except Exception as exc:
        logger.error("AI email generation failed: %s", exc, exc_info=True)
        raise HTTPException(400, f"AI generation failed: {exc}")
    logger.info("AI email response received")

    await db.applications.update_one(
        {"id": application["id"]},
        {"$set": {
            "resume_id": resume["id"],
            "subject": email["subject"],
            "body": email["body"],
            "recipient_email": application.get("hr_email")
        }}
    )

    return GeneratedEmailOut(subject=email["subject"], body=email["body"])


async def _create_draft_application(db: AsyncIOMotorDatabase, user: dict, details: dict) -> dict:
    resume = await db.resumes.find_one({"user_id": user["id"], "is_default": True})
    if resume is None:
        raise HTTPException(400, "Upload a resume first")

    application = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "resume_id": resume["id"],
        "job_title": details["jobTitle"],
        "company": details["company"],
        "location": details.get("location"),
        "job_summary": details["summary"],
        "key_requirements": details["keyRequirements"],
        "source_type": details["sourceType"],
        "source_raw": details["sourceRaw"][:5000],
        "hr_email": details.get("hrEmail"),
        "hr_name": details.get("hrName"),
        "recipient_email": details.get("hrEmail"),
        "subject": "",
        "body": "",
        "status": "draft",
        "created_at": datetime.utcnow(),
        "sent_at": None,
        "follow_ups": [],
        "ai_suggestions": []
    }
    await db.applications.insert_one(application)
    return application


def _to_extracted_job_out(a: dict) -> ExtractedJobOut:
    return ExtractedJobOut(
        id=a["id"],
        jobTitle=a["job_title"],
        company=a["company"],
        location=a.get("location"),
        hrEmail=a.get("hr_email"),
        hrName=a.get("hr_name"),
        summary=a["job_summary"],
        keyRequirements=a["key_requirements"],
        sourceType=a["source_type"],
        sourceRaw=a["source_raw"],
    )
