from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
import uuid
from datetime import datetime

from app.db.session import get_db
from app.schemas.auth import GoogleLoginRequest, LoginResponse, UserOut
from app.services.google_oauth import verify_google_id_token, exchange_code_for_tokens
from app.services.jwt_service import create_access_token
from app.api.deps import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/google", response_model=LoginResponse)
async def google_login(payload: GoogleLoginRequest, db: AsyncIOMotorDatabase = Depends(get_db)):
    """Handles both:
    - auth-code flow: payload.code is set → exchanges code for tokens, stores refresh_token
    - id_token flow: payload.id_token is set → verifies the token (no gmail.send scope)
    """
    refresh_token = None

    if payload.code:
        # Auth-code flow: exchange code for tokens and get user info
        try:
            tokens = exchange_code_for_tokens(payload.code)
        except Exception as e:
            raise HTTPException(401, f"Failed to exchange auth code: {e}")

        refresh_token = tokens.get("refresh_token")
        id_token_str = tokens.get("id_token")
        if not id_token_str:
            raise HTTPException(401, "No id_token in token response")

        try:
            info = verify_google_id_token(id_token_str)
        except Exception as e:
            raise HTTPException(401, f"Invalid id_token from Google: {e}")

    elif payload.id_token:
        # Fallback: id_token only (no gmail.send scope)
        try:
            info = verify_google_id_token(payload.id_token)
        except Exception as e:
            raise HTTPException(401, f"Invalid Google token: {e}")
    else:
        raise HTTPException(400, "Either code or id_token is required")

    user = await db.users.find_one({"google_sub": info["sub"]})

    if user is None:
        user = {
            "id": str(uuid.uuid4()),
            "google_sub": info["sub"],
            "email": info["email"],
            "name": info.get("name", info["email"]),
            "avatar_url": info.get("picture"),
            "google_refresh_token": refresh_token,
            "created_at": datetime.utcnow()
        }
        await db.users.insert_one(user)
    else:
        # Update refresh token if we got one (auth-code flow)
        if refresh_token:
            await db.users.update_one(
                {"google_sub": info["sub"]},
                {"$set": {"google_refresh_token": refresh_token}}
            )
            user["google_refresh_token"] = refresh_token

    token = create_access_token(user["id"])
    return LoginResponse(
        user=UserOut(
            id=user["id"], 
            name=user["name"], 
            email=user["email"], 
            avatarUrl=user.get("avatar_url"),
            hasGmailAccess=bool(user.get("google_refresh_token"))
        ),
        token=token,
    )


@router.get("/me", response_model=UserOut)
async def me(user: dict = Depends(get_current_user)):
    return UserOut(
        id=user["id"], 
        name=user["name"], 
        email=user["email"], 
        avatarUrl=user.get("avatar_url"),
        hasGmailAccess=bool(user.get("google_refresh_token"))
    )


@router.post("/logout")
async def logout(user: dict = Depends(get_current_user)):
    return {"ok": True}
