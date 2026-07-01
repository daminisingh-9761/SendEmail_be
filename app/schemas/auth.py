from pydantic import BaseModel, EmailStr


class GoogleLoginRequest(BaseModel):
    id_token: str | None = None
    code: str | None = None


class UserOut(BaseModel):
    id: str
    name: str
    email: EmailStr
    avatarUrl: str | None = None
    hasGmailAccess: bool = False

    class Config:
        from_attributes = True


class LoginResponse(BaseModel):
    user: UserOut
    token: str
