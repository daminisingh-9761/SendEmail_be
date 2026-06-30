"""Sends mail through the Gmail API using the signed-in user's own OAuth
credentials (gmail.send scope), so the email arrives from their address with
their reply-to intact. Falls back to raising a clear error if the user's
Google grant doesn't include send permission, which the API layer surfaces
to the frontend as a re-auth prompt.
"""
import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from app.core.config import get_settings

settings = get_settings()


def _build_credentials(refresh_token: str) -> Credentials:
    return Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=[settings.google_send_scopes],
    )


def send_email_with_attachment(
    refresh_token: str,
    sender_email: str,
    to: str,
    subject: str,
    body: str,
    attachment_bytes: bytes,
    attachment_filename: str,
) -> str:
    creds = _build_credentials(refresh_token)
    service = build("gmail", "v1", credentials=creds)

    message = MIMEMultipart()
    message["to"] = to
    message["from"] = sender_email
    message["subject"] = subject
    message.attach(MIMEText(body, "plain"))

    part = MIMEApplication(attachment_bytes, Name=attachment_filename)
    part["Content-Disposition"] = f'attachment; filename="{attachment_filename}"'
    message.attach(part)

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
    return sent["id"]
