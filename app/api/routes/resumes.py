from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime
import uuid

from app.db.session import get_db
from app.schemas.resume import ResumeOut
from app.api.deps import get_current_user
from app.core.config import get_settings
from app.services import storage as storage_service

router = APIRouter(prefix="/resumes", tags=["resumes"])
settings = get_settings()


@router.get("", response_model=list[ResumeOut])
async def list_resumes(user: dict = Depends(get_current_user), db: AsyncIOMotorDatabase = Depends(get_db)):
    cursor = db.resumes.find({"user_id": user["id"]}).sort("uploaded_at", -1)
    resumes = await cursor.to_list(length=100)
    
    valid_resumes = []
    for r in resumes:
        if storage_service.file_exists(r["storage_path"]):
            valid_resumes.append(r)
        else:
            await db.resumes.delete_one({"id": r["id"]})

    return [
        ResumeOut(id=r["id"], fileName=r["file_name"], uploadedAt=r["uploaded_at"], sizeKb=r.get("size_kb", 0))
        for r in valid_resumes
    ]

print("Resume upload endpoint called")
@router.post("", response_model=list[ResumeOut])
async def upload_resume(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    contents = await file.read()
    # Upload to Supabase Storage instead of local folder
    storage_path = storage_service.upload_resume(file.filename, contents)

    resume = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "file_name": file.filename,
        "storage_path": storage_path,
        "size_kb": max(1, len(contents) // 1024),
        "uploaded_at": datetime.utcnow()
    }
    result = await db.resumes.insert_one(resume)
    
    print("Inserted ID:", result.inserted_id)
    
    # Return the updated list of resumes
    cursor = db.resumes.find({"user_id": user["id"]}).sort("uploaded_at", -1)
    resumes = await cursor.to_list(length=100)
    
    valid_resumes = []
    for r in resumes:
        if storage_service.file_exists(r["storage_path"]):
            valid_resumes.append(r)
        else:
            await db.resumes.delete_one({"id": r["id"]})

    return [
        ResumeOut(id=r["id"], fileName=r["file_name"], uploadedAt=r["uploaded_at"], sizeKb=r.get("size_kb", 0))
        for r in valid_resumes
    ]

@router.delete("/{resume_id}")
async def delete_resume(
    resume_id: str, 
    user: dict = Depends(get_current_user), 
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    r = await db.resumes.find_one({"id": resume_id, "user_id": user["id"]})
    if not r:
        raise HTTPException(404, "Resume not found")

    try:
        storage_service.delete_resume(r["storage_path"])
    except Exception as e:
        print(f"Error deleting file from storage: {e}")
        # Continue to delete from DB even if storage deletion fails
        
    await db.resumes.delete_one({"id": resume_id})
    return {"message": "Resume deleted successfully"}
