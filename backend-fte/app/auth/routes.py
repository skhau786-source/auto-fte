from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.schemas import SignupRequest, LoginRequest, GoogleLoginRequest, AuthResponse, UserOut
from app.models import LoginMethod, RegisteredStudent
from app.security import create_access_token
from app.auth import service

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _auth_response(message: str, user: RegisteredStudent) -> AuthResponse:
    """Build an AuthResponse that includes a signed JWT access token."""
    token = create_access_token({"sub": str(user.id)})
    return AuthResponse(
        message=message,
        user=UserOut.model_validate(user),
        access_token=token,
        token_type="bearer",
    )


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def signup(payload: SignupRequest, request: Request, db: AsyncSession = Depends(get_db)):
    user = await service.create_local_user(db, payload)
    await service.log_login(db, user, LoginMethod.LOCAL, request)
    return _auth_response("Signup successful", user)


@router.post("/login", response_model=AuthResponse)
async def login(payload: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    user = await service.authenticate_local_user(db, payload.email, payload.password)
    await service.log_login(db, user, LoginMethod.LOCAL, request)
    return _auth_response("Login successful", user)


@router.post("/google", response_model=AuthResponse)
async def google_login(payload: GoogleLoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    user = await service.get_or_create_google_user(db, payload.id_token)
    await service.log_login(db, user, LoginMethod.GOOGLE, request)
    return _auth_response("Google login successful", user)


@router.get("/me", response_model=AuthResponse)
async def me(user: RegisteredStudent = Depends(get_current_user)):
    """Return the currently authenticated user — used to restore sessions."""
    return _auth_response("Authenticated", user)
