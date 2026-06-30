"""Verifies Google Sign-In ID tokens and manages the OAuth flow used to
later send Gmail on the user's behalf (gmail.send scope, incremental auth)."""
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests
from app.core.config import get_settings

settings = get_settings()


def verify_google_id_token(token: str) -> dict:
    """Returns the verified payload {sub, email, name, picture} or raises ValueError."""
    payload = google_id_token.verify_oauth2_token(
        token, google_requests.Request(), settings.google_client_id
    )
    if payload.get("aud") != settings.google_client_id:
        raise ValueError("Invalid audience")
    return payload
