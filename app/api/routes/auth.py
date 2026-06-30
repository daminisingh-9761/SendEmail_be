from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
import uuid
from datetime import datetime

from app.db.session import get_db
from app.schemas.auth import GoogleLoginRequest, LoginResponse, UserOut
from app.services.google_oauth import verify_google_id_token
from app.services.jwt_service import create_access_token
from app.api.deps import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])

# @router.post("/google", response_model=LoginResponse)
# async def google_login(payload: GoogleLoginRequest, db: AsyncIOMotorDatabase = Depends(get_db)):
#     try:
#         info = verify_google_id_token(payload.id_token)
#     except ValueError:
#         raise HTTPException(401, "Invalid Google token")
@router.post("/google", response_model=LoginResponse)
async def google_login(payload: GoogleLoginRequest, db: AsyncIOMotorDatabase = Depends(get_db)):
    try:
        info = verify_google_id_token(payload.id_token)
        print("Verified payload:", info)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=401, detail=str(e))

    user = await db.users.find_one({"google_sub": info["sub"]})

    if user is None:
        user = {
            "id": str(uuid.uuid4()),
            "google_sub": info["sub"],
            "email": info["email"],
            "name": info.get("name", info["email"]),
            "avatar_url": info.get("picture"),
            "created_at": datetime.utcnow()
        }
        await db.users.insert_one(user)

    token = create_access_token(user["id"])
    return LoginResponse(
        user=UserOut(id=user["id"], name=user["name"], email=user["email"], avatarUrl=user.get("avatar_url")),
        token=token,
    )


@router.get("/me", response_model=UserOut)
async def me(user: dict = Depends(get_current_user)):
    return UserOut(id=user["id"], name=user["name"], email=user["email"], avatarUrl=user.get("avatar_url"))


@router.post("/logout")
async def logout(user: dict = Depends(get_current_user)):
    return {"ok": True}
