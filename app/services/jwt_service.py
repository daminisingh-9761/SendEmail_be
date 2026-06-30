from datetime import datetime, timedelta, timezone
from jose import jwt
from app.core.config import get_settings

settings = get_settings()
ALGORITHM = "HS256"


def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> str:
    payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    return payload["sub"]
