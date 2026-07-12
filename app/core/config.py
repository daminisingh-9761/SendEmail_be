from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    # Environment
    env: str = "development"
    secret_key: str = "dev-secret"
    frontend_urls: str = "http://localhost:5173"

    # MongoDB
    mongodb_url: str
    mongodb_db_name: str

    # Google OAuth
    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str = "http://localhost:8000/api/auth/google/callback"
    google_send_scopes: str = "https://www.googleapis.com/auth/gmail.send"

    # AI
    ai_provider: str = "openai"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-flash"

    # Storage (local / S3 legacy)
    storage_backend: str = "local"
    storage_local_dir: str = "./uploads"
    s3_bucket: str = ""
    s3_region: str = ""

    # Supabase Storage
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_bucket: str = "resumes"

    # JWT
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days


@lru_cache
def get_settings() -> Settings:
    return Settings()