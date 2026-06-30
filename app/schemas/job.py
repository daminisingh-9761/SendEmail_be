from pydantic import BaseModel


class JobExtractTextRequest(BaseModel):
    type: str  # "text" | "url"
    text: str | None = None
    url: str | None = None


class ExtractedJobOut(BaseModel):
    id: str
    jobTitle: str
    company: str
    location: str | None = None
    hrEmail: str | None = None
    hrName: str | None = None
    summary: str
    keyRequirements: list[str]
    sourceType: str
    sourceRaw: str


class GenerateEmailRequest(BaseModel):
    jobId: str
    resumeId: str


class GeneratedEmailOut(BaseModel):
    subject: str
    body: str
