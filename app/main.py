from contextlib import asynccontextmanager
from fastapi import FastAPI
import pymongo
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.api.routes import auth, resumes, jobs, applications

settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.db.session import db
    # Index for fetching applications by user and sorting by date
    await db.applications.create_index([
        ("user_id", pymongo.ASCENDING),
        ("created_at", pymongo.DESCENDING)
    ])
    # Index for filtering applications by status
    await db.applications.create_index([
        ("user_id", pymongo.ASCENDING),
        ("status", pymongo.ASCENDING),
        ("created_at", pymongo.DESCENDING)
    ])
    yield

app = FastAPI(title="Mailjob API", version="1.0.0", lifespan=lifespan)

origins = [url.strip() for url in settings.frontend_urls.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"https://.*\.ngrok-free\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(resumes.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")
app.include_router(applications.router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok"}
