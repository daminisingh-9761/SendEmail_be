"""Background email sending so the API request returns immediately and the
UI can show a 'sending' state without holding the HTTP connection open.
Retries with backoff if Gmail's API is briefly unavailable.
"""
import asyncio
import base64
from datetime import datetime, timezone
import logging
from tenacity import retry, stop_after_attempt, wait_exponential

from app.services.gmail_sender import send_email_with_attachment
from app.db.session import db

logger = logging.getLogger(__name__)

@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=2, max=10))
def _send_email_sync(refresh_token, sender_email, to, subject, body, attachment_bytes, attachment_filename):
    return send_email_with_attachment(
        refresh_token, sender_email, to, subject, body, attachment_bytes, attachment_filename
    )

async def send_application_email_task(
    
    refresh_token: str, sender_email: str, to: str, subject: str,
    body: str, attachment_bytes_b64: str, attachment_filename: str, application_id: str,
):
    print("========== BACKGROUND TASK STARTED ==========")
    attachment_bytes = base64.b64decode(attachment_bytes_b64)

    try:
        message_id = await asyncio.to_thread(
            _send_email_sync, refresh_token, sender_email, to, subject, body, attachment_bytes, attachment_filename
        )
        logger.info(f"Email sent for application {application_id}, message_id={message_id}")
    except Exception as exc:
        logger.error(f"Failed to send email for application {application_id}: {exc}")
        await db.applications.update_one(
            {"id": application_id},
            {"$set": {"status": "failed"}}
        )
        return

    await db.applications.update_one(
        {"id": application_id},
        {"$set": {
            "status": "sent",
            "sent_at": datetime.now(timezone.utc)
        }}
    )
