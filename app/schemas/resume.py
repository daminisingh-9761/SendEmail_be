from datetime import datetime
from pydantic import BaseModel


class ResumeOut(BaseModel):
    id: str
    fileName: str
    uploadedAt: datetime
    sizeKb: int

    class Config:
        from_attributes = True
