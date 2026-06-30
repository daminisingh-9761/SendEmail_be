from pydantic import BaseModel, EmailStr


class GoogleLoginRequest(BaseModel):
    id_token: str


class UserOut(BaseModel):
    id: str
    name: str
    email: EmailStr
    avatarUrl: str | None = None

    class Config:
        from_attributes = True


class LoginResponse(BaseModel):
    user: UserOut
    token: str
