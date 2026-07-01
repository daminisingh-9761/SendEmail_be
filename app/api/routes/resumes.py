from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime
import os, uuid

from app.db.session import get_db
from app.schemas.resume import ResumeOut
from app.api.deps import get_current_user
from app.core.config import get_settings

router = APIRouter(prefix="/resumes", tags=["resumes"])
settings = get_settings()


@router.get("", response_model=list[ResumeOut])
async def list_resumes(user: dict = Depends(get_current_user), db: AsyncIOMotorDatabase = Depends(get_db)):
    cursor = db.resumes.find({"user_id": user["id"]}).sort("uploaded_at", -1)
    resumes = await cursor.to_list(length=100)
    return [
        ResumeOut(id=r["id"], fileName=r["file_name"], uploadedAt=r["uploaded_at"], isDefault=r.get("is_default", False), sizeKb=r.get("size_kb", 0))
        for r in resumes
    ]

print("Resume upload endpoint called")
@router.post("", response_model=ResumeOut)
async def upload_resume(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    os.makedirs(settings.storage_local_dir, exist_ok=True)
    contents = await file.read()
    storage_name = f"{uuid.uuid4()}_{file.filename}"
    storage_path = os.path.join(settings.storage_local_dir, storage_name)
    with open(storage_path, "wb") as f:
        f.write(contents)

    # New uploads become the default resume going forward.
    await db.resumes.update_many({"user_id": user["id"]}, {"$set": {"is_default": False}})

    resume = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "file_name": file.filename,
        "storage_path": storage_path,
        "size_kb": max(1, len(contents) // 1024),
        "is_default": True,
        "uploaded_at": datetime.utcnow()
    }
    result = await db.resumes.insert_one(resume)
    print("Inserted ID:", result.inserted_id)
    

    return ResumeOut(
        id=resume["id"], fileName=resume["file_name"], uploadedAt=resume["uploaded_at"],
        isDefault=resume["is_default"], sizeKb=resume["size_kb"],
    )


@router.patch("/{resume_id}/default", response_model=ResumeOut)
async def set_default_resume(resume_id: str, user: dict = Depends(get_current_user), db: AsyncIOMotorDatabase = Depends(get_db)):
    await db.resumes.update_many({"user_id": user["id"]}, {"$set": {"is_default": False}})
    await db.resumes.update_one({"id": resume_id, "user_id": user["id"]}, {"$set": {"is_default": True}})
    
    r = await db.resumes.find_one({"id": resume_id})
    if not r:
        raise HTTPException(404, "Resume not found")
        
    return ResumeOut(id=r["id"], fileName=r["file_name"], uploadedAt=r["uploaded_at"], isDefault=r.get("is_default", False), sizeKb=r.get("size_kb", 0))
