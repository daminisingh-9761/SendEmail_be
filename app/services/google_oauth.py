"""Verifies Google Sign-In ID tokens and manages the OAuth flow used to
later send Gmail on the user's behalf (gmail.send scope, incremental auth)."""
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests
from app.core.config import get_settings
import requests as http_requests

settings = get_settings()


def verify_google_id_token(token: str) -> dict:
    """Returns the verified payload {sub, email, name, picture} or raises ValueError."""
    payload = google_id_token.verify_oauth2_token(
        token, google_requests.Request(), settings.google_client_id
    )
    if payload.get("aud") != settings.google_client_id:
        raise ValueError("Invalid audience")
    return payload


def exchange_code_for_tokens(code: str) -> dict:
    """Exchanges an authorization code for access + refresh tokens.
    Returns dict with keys: access_token, refresh_token, id_token (and others).
    """
    resp = http_requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": "postmessage",  # Required for auth-code flow from browser
            "grant_type": "authorization_code",
        },
    )
    resp.raise_for_status()
    return resp.json()
