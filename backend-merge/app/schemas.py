import uuid
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, field_validator


class SignupRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class GoogleLoginRequest(BaseModel):
    id_token: str


class UserOut(BaseModel):
    id: uuid.UUID
    username: str
    email: str
    full_name: str | None
    auth_provider: str
    is_verified: bool
    created_at: datetime

    class Config:
        from_attributes = True


class AuthResponse(BaseModel):
    message: str
    user: UserOut
