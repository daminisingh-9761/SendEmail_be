from datetime import datetime
from pydantic import BaseModel, EmailStr


class SendEmailRequest(BaseModel):
    recipientEmail: EmailStr
    subject: str
    body: str


class EditEmailRequest(BaseModel):
    instruction: str


class FollowUpOut(BaseModel):
    id: str
    sentAt: datetime
    body: str


class JobOut(BaseModel):
    jobTitle: str
    company: str
    location: str | None = None
    hrEmail: str | None = None
    hrName: str | None = None
    summary: str
    keyRequirements: list[str]
    sourceType: str
    sourceRaw: str


class EmailOut(BaseModel):
    subject: str
    body: str


class ApplicationOut(BaseModel):
    id: str
    job: JobOut
    email: EmailOut
    recipientEmail: str
    resumeId: str
    resumeFileName: str
    status: str
    createdAt: datetime
    sentAt: datetime | None = None
    followUps: list[FollowUpOut]
    aiSuggestions: list[str]


class PaginatedApplicationsOut(BaseModel):
    items: list[ApplicationOut]
    total: int
    page: int
    pages: int
    limit: int


class DeleteApplicationsRequest(BaseModel):
    ids: list[str]
