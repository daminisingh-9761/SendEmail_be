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
        ResumeOut(id=r["id"], fileName=r["file_name"], uploadedAt=r["uploaded_at"], isDefault=r.get("is_default", False), sizeKb=r.get("size_kb", 0))
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
        "is_default": False,
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
        ResumeOut(id=r["id"], fileName=r["file_name"], uploadedAt=r["uploaded_at"], isDefault=r.get("is_default", False), sizeKb=r.get("size_kb", 0))
        for r in valid_resumes
    ]

@router.patch("/{resume_id}/default", response_model=list[ResumeOut])
async def set_default_resume(
    resume_id: str, 
    user: dict = Depends(get_current_user), 
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    r = await db.resumes.find_one({"id": resume_id, "user_id": user["id"]})
    if not r:
        raise HTTPException(404, "Resume not found")

    await db.resumes.update_many(
        {"user_id": user["id"], "id": {"$ne": resume_id}},
        {"$set": {"is_default": False}}
    )
    await db.resumes.update_one(
        {"id": resume_id, "user_id": user["id"]},
        {"$set": {"is_default": True}}
    )
    
    cursor = db.resumes.find({"user_id": user["id"]}).sort("uploaded_at", -1)
    resumes = await cursor.to_list(length=100)
    
    valid_resumes = []
    for res in resumes:
        if storage_service.file_exists(res["storage_path"]):
            valid_resumes.append(res)
        else:
            await db.resumes.delete_one({"id": res["id"]})

    return [
        ResumeOut(id=r["id"], fileName=r["file_name"], uploadedAt=r["uploaded_at"], isDefault=r.get("is_default", False), sizeKb=r.get("size_kb", 0))
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

from app.schemas.resume import PreviewUrlOut

@router.get("/{resume_id}/preview", response_model=PreviewUrlOut)
async def preview_resume(
    resume_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    # Requirement 6: 404 if resume doesn't exist, 403 if it belongs to another user
    resume = await db.resumes.find_one({"id": resume_id})
    if not resume:
        raise HTTPException(404, "Resume not found")
        
    if resume["user_id"] != user["id"]:
        raise HTTPException(403, "Forbidden: You do not have permission to view this resume")
        
    try:
        # Create signed URL valid for 10 minutes (600 seconds)
        signed_url = storage_service.create_signed_url(resume["storage_path"], 600)
        return PreviewUrlOut(previewUrl=signed_url)
    except Exception as e:
        print(f"Error generating preview URL: {e}")
        raise HTTPException(500, "Could not generate preview URL")
