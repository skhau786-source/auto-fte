from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import SignupRequest, LoginRequest, GoogleLoginRequest, AuthResponse, UserOut
from app.models import LoginMethod
from app.auth import service

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def signup(payload: SignupRequest, request: Request, db: AsyncSession = Depends(get_db)):
    user = await service.create_local_user(db, payload)
    await service.log_login(db, user, LoginMethod.LOCAL, request)
    return AuthResponse(message="Signup successful", user=UserOut.model_validate(user))


@router.post("/login", response_model=AuthResponse)
async def login(payload: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    user = await service.authenticate_local_user(db, payload.email, payload.password)
    await service.log_login(db, user, LoginMethod.LOCAL, request)
    return AuthResponse(message="Login successful", user=UserOut.model_validate(user))


@router.post("/google", response_model=AuthResponse)
async def google_login(payload: GoogleLoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    user = await service.get_or_create_google_user(db, payload.id_token)
    await service.log_login(db, user, LoginMethod.GOOGLE, request)
    return AuthResponse(message="Google login successful", user=UserOut.model_validate(user))