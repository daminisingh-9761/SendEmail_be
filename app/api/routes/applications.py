import base64
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.session import get_db
from app.schemas.application import SendEmailRequest, EditEmailRequest, ApplicationOut, JobOut, EmailOut, FollowUpOut
from app.api.deps import get_current_user
from app.services.ai_provider import get_ai_provider
from app.tasks.email_tasks import send_application_email_task
from app.services import storage as storage_service
from app.services.resume_text import extract_resume_text

router = APIRouter(prefix="/applications", tags=["applications"])


@router.get("", response_model=list[ApplicationOut])
async def list_applications(user: dict = Depends(get_current_user), db: AsyncIOMotorDatabase = Depends(get_db)):
    cursor = db.applications.find({"user_id": user["id"]}).sort("created_at", -1)
    apps = await cursor.to_list(length=100)
    out = []
    for a in apps:
        out.append(await _to_out(db, a))
    return out


@router.get("/{application_id}", response_model=ApplicationOut)
async def get_application(application_id: str, user: dict = Depends(get_current_user), db: AsyncIOMotorDatabase = Depends(get_db)):
    a = await db.applications.find_one({"id": application_id})
    if a is None or a["user_id"] != user["id"]:
        raise HTTPException(404, "Not found")
    return await _to_out(db, a)


@router.post("/{application_id}/send", response_model=ApplicationOut)
async def send_application(
    application_id: str,
    payload: SendEmailRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    a = await db.applications.find_one({"id": application_id})
    if a is None or a["user_id"] != user["id"]:
        raise HTTPException(404, "Not found")

    if not user.get("google_refresh_token"):
        raise HTTPException(
            428,
            "Mail-send permission required. Please sign out and sign in again with Google to grant Gmail access.",
        )
    refresh_token = user["google_refresh_token"]

    resume = await db.resumes.find_one({"id": a["resume_id"]})
    if resume is None:
        raise HTTPException(400, "No resume attached")

    await db.applications.update_one(
        {"id": application_id},
        {"$set": {
            "recipient_email": payload.recipientEmail,
            "subject": payload.subject,
            "body": payload.body
        }}
    )
    a = await db.applications.find_one({"id": application_id})

    # Download resume bytes from Supabase Storage
    try:
        attachment_bytes = storage_service.download_resume(resume["storage_path"])
    except Exception as e:
        raise HTTPException(400, "The associated resume file is missing or inaccessible. Please upload a new resume.")

    # Queue the actual send using BackgroundTasks
    background_tasks.add_task(
        send_application_email_task,
        refresh_token,
        user.get("email", ""),
        payload.recipientEmail,
        payload.subject,
        payload.body,
        base64.b64encode(attachment_bytes).decode(),
        resume["file_name"],
        a["id"],
    )

    return await _to_out(db, a)


@router.post("/{application_id}/resend", response_model=ApplicationOut)
async def resend_application(
    application_id: str,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    a = await db.applications.find_one({"id": application_id})
    if a is None or a["user_id"] != user["id"]:
        raise HTTPException(404, "Not found")
    refresh_token = user.get("google_refresh_token")
    if not refresh_token:
        raise HTTPException(428, "Mail-send permission required. Please sign in again.")

    resume = await db.resumes.find_one({"id": a["resume_id"]})
    # Download resume bytes from Supabase Storage
    try:
        attachment_bytes = storage_service.download_resume(resume["storage_path"])
    except Exception as e:
        raise HTTPException(400, "The associated resume file is missing or inaccessible. Please upload a new resume.")

    background_tasks.add_task(
        send_application_email_task,
        refresh_token,
        user.get("email", ""),
        a["recipient_email"],
        a["subject"],
        a["body"],
        base64.b64encode(attachment_bytes).decode(),
        resume["file_name"],
        a["id"],
    )
    return await _to_out(db, a)


@router.post("/{application_id}/regenerate", response_model=ApplicationOut)
async def regenerate_email(
    application_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    a = await db.applications.find_one({"id": application_id})
    if a is None or a["user_id"] != user["id"]:
        raise HTTPException(404, "Not found")

    resume = await db.resumes.find_one({"id": a["resume_id"]})
    if not resume:
        raise HTTPException(400, "Resume not found for this application")

    try:
        resume_text = extract_resume_text(resume["storage_path"])
    except Exception as e:
        raise HTTPException(400, "The associated resume file is missing or inaccessible. Please upload a new resume.")
    job_dict = {
        "jobTitle": a.get("job_title"),
        "company": a.get("company"),
        "summary": a.get("job_summary"),
        "keyRequirements": a.get("key_requirements", []),
        "location": a.get("location"),
        "hrEmail": a.get("hr_email"),
        "hrName": a.get("hr_name")
    }

    ai = get_ai_provider()
    new_email = await ai.regenerate_email(
        job=job_dict,
        resume_text=resume_text,
        previous_subject=a.get("subject", ""),
        previous_body=a.get("body", "")
    )

    await db.applications.update_one(
        {"id": application_id},
        {"$set": {
            "subject": new_email.get("subject", a.get("subject")),
            "body": new_email.get("body", a.get("body"))
        }}
    )
    
    a = await db.applications.find_one({"id": application_id})
    return await _to_out(db, a)


@router.post("/{application_id}/edit", response_model=ApplicationOut)
async def edit_email(
    application_id: str,
    payload: EditEmailRequest,
    user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    a = await db.applications.find_one({"id": application_id})
    if a is None or a["user_id"] != user["id"]:
        raise HTTPException(404, "Not found")

    resume = await db.resumes.find_one({"id": a["resume_id"]})
    if not resume:
        raise HTTPException(400, "Resume not found for this application")

    try:
        resume_text = extract_resume_text(resume["storage_path"])
    except Exception as e:
        raise HTTPException(400, "The associated resume file is missing or inaccessible. Please upload a new resume.")
    
    job_dict = {
        "jobTitle": a.get("job_title"),
        "company": a.get("company"),
        "summary": a.get("job_summary"),
        "keyRequirements": a.get("key_requirements", []),
        "location": a.get("location"),
        "hrEmail": a.get("hr_email"),
        "hrName": a.get("hr_name")
    }

    ai = get_ai_provider()
    edited_email = await ai.edit_email(
        job=job_dict,
        resume_text=resume_text,
        current_subject=a.get("subject", ""),
        current_body=a.get("body", ""),
        instruction=payload.instruction
    )

    await db.applications.update_one(
        {"id": application_id},
        {"$set": {
            "subject": edited_email.get("subject", a.get("subject")),
            "body": edited_email.get("body", a.get("body"))
        }}
    )
    
    a = await db.applications.find_one({"id": application_id})
    return await _to_out(db, a)


@router.post("/{application_id}/follow-up", response_model=ApplicationOut)
async def follow_up(
    application_id: str,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    a = await db.applications.find_one({"id": application_id})
    if a is None or a["user_id"] != user["id"]:
        raise HTTPException(404, "Not found")
    refresh_token = user.get("google_refresh_token")
    if not refresh_token:
        raise HTTPException(428, "Mail-send permission required. Please sign in again.")

    ai = get_ai_provider()
    job_dict = {"jobTitle": a["job_title"], "company": a["company"], "summary": a["job_summary"]}
    follow_up_body = await ai.generate_follow_up(job_dict, a["body"])

    resume = await db.resumes.find_one({"id": a["resume_id"]})
    # Download resume bytes from Supabase Storage
    try:
        attachment_bytes = storage_service.download_resume(resume["storage_path"])
    except Exception as e:
        raise HTTPException(400, "The associated resume file is missing or inaccessible. Please upload a new resume.")

    subject = f"Following up: {a['subject']}"
    background_tasks.add_task(
        send_application_email_task,
        refresh_token,
        user.get("email", ""),
        a["recipient_email"],
        subject,
        follow_up_body,
        base64.b64encode(attachment_bytes).decode(),
        resume["file_name"],
        a["id"],
    )

    follow_up_doc = {
        "id": str(uuid.uuid4()),
        "application_id": a["id"],
        "body": follow_up_body,
        "sent_at": datetime.utcnow()
    }
    
    await db.applications.update_one(
        {"id": a["id"]},
        {"$set": {"status": "follow_up_sent"}, "$push": {"follow_ups": follow_up_doc}}
    )
    a = await db.applications.find_one({"id": application_id})
    
    return await _to_out(db, a)


async def _to_out(db: AsyncIOMotorDatabase, a: dict) -> ApplicationOut:
    resume = await db.resumes.find_one({"id": a["resume_id"]})
    follow_ups = a.get("follow_ups", [])

    return ApplicationOut(
        id=a["id"],
        job=JobOut(
            jobTitle=a["job_title"], company=a["company"], location=a.get("location"), hrEmail=a.get("hr_email"),
            hrName=a.get("hr_name"), summary=a["job_summary"], keyRequirements=a["key_requirements"],
            sourceType=a["source_type"], sourceRaw=a["source_raw"],
        ),
        email=EmailOut(subject=a.get("subject") or "", body=a.get("body") or ""),
        recipientEmail=a.get("recipient_email") or "",
        resumeId=a["resume_id"],
        resumeFileName=resume["file_name"] if resume else "",
        status=a["status"],
        createdAt=a["created_at"],
        sentAt=a.get("sent_at"),
        followUps=[FollowUpOut(id=f["id"], sentAt=f["sent_at"], body=f["body"]) for f in follow_ups],
        aiSuggestions=a.get("ai_suggestions") or [],
    )
