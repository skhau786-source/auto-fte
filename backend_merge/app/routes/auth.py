from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.login_log import LoginMethod
from app.models.user import User
from app.schemas.auth_schema import (
    AuthResponse,
    ForgotPasswordRequest,
    GoogleLoginRequest,
    LoginRequest,
    MessageResponse,
    ResetPasswordRequest,
    SignupRequest,
    UserOut,
)
from app.security import create_access_token, decode_access_token, hash_password
from app.services import auth_service
from app.services.email_service import send_email
from app.services.rate_limiter import login_rate_limiter

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _client_info(request: Request):
    """Request se IP + user-agent nikalta hai (login log ke liye)."""
    ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    return ip, user_agent


def _decode_typed_token(token: str, expected_type: str) -> dict:
    """Email-verify / reset-password wale typed tokens ko decode karta hai."""
    try:
        payload = decode_access_token(token)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    if payload.get("type") != expected_type or not payload.get("sub"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token type")
    return payload


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, request: Request, db: Session = Depends(get_db)):
    """Naya user banao (username + email + password). Kamyabi par token milta hai."""
    user = auth_service.create_local_user(db, payload)
    auth_service.log_login(db, user, LoginMethod.LOCAL, *_client_info(request))
    token = create_access_token({"sub": str(user.id)})
    return AuthResponse(
        message="Signup successful",
        access_token=token,
        user=UserOut.model_validate(user),
    )


@router.post("/login", response_model=AuthResponse)
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(login_rate_limiter),
):
    """Email + password se login. Sahi hone par access_token milta hai."""
    user = auth_service.authenticate_local_user(db, payload.email, payload.password)
    auth_service.log_login(db, user, LoginMethod.LOCAL, *_client_info(request))
    token = create_access_token({"sub": str(user.id)})
    return AuthResponse(
        message="Login successful",
        access_token=token,
        user=UserOut.model_validate(user),
    )


@router.post("/google", response_model=AuthResponse)
def google_login(payload: GoogleLoginRequest, request: Request, db: Session = Depends(get_db)):
    """Google id_token se login (frontend Google Sign-In se token bhejta hai)."""
    user = auth_service.get_or_create_google_user(db, payload.id_token)
    auth_service.log_login(db, user, LoginMethod.GOOGLE, *_client_info(request))
    token = create_access_token({"sub": str(user.id)})
    return AuthResponse(
        message="Google login successful",
        access_token=token,
        user=UserOut.model_validate(user),
    )


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(auth_service.get_current_user)):
    """Token ke zariye current logged-in user ki details."""
    return current_user


@router.post("/send-verification", response_model=MessageResponse)
def send_verification(current_user: User = Depends(auth_service.get_current_user)):
    """Logged-in user ko email verification link bhejta hai."""
    if current_user.is_verified:
        return MessageResponse(message="Email already verified")

    token = create_access_token(
        {"sub": str(current_user.id), "type": "email_verify"},
        expires_delta=timedelta(hours=24),
    )
    link = f"{settings.FRONTEND_URL}/verify-email?token={token}"
    send_email(
        current_user.email,
        "Email verify karein",
        f"<p>Apna email verify karne ke liye click karein:</p><p><a href='{link}'>{link}</a></p>",
    )
    return MessageResponse(message="Verification email bhej di gayi")


@router.get("/verify-email", response_model=MessageResponse)
def verify_email(token: str, db: Session = Depends(get_db)):
    """Email verification link ko verify karta hai (is_verified = true)."""
    payload = _decode_typed_token(token, "email_verify")
    user = db.query(User).filter(User.id == int(payload["sub"])).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.is_verified = True
    db.commit()
    return MessageResponse(message="Email verified successfully")


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(
    payload: ForgotPasswordRequest,
    db: Session = Depends(get_db),
    _: None = Depends(login_rate_limiter),
):
    """Password reset link email par bhejta hai (email na ho to bhi same response)."""
    user = db.query(User).filter(User.email == payload.email).first()
    if user:
        token = create_access_token(
            {"sub": str(user.id), "type": "reset_password"},
            expires_delta=timedelta(minutes=30),
        )
        link = f"{settings.FRONTEND_URL}/reset-password?token={token}"
        send_email(
            user.email,
            "Password reset",
            f"<p>Naya password set karne ke liye click karein:</p><p><a href='{link}'>{link}</a></p>",
        )
    # user enumeration se bachne ke liye hamesha same message
    return MessageResponse(message="Agar email maujood hai to reset link bhej diya gaya")


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    """Reset link se naya password set karta hai."""
    decoded = _decode_typed_token(payload.token, "reset_password")
    user = db.query(User).filter(User.id == int(decoded["sub"])).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.hashed_password = hash_password(payload.new_password)
    db.commit()
    return MessageResponse(message="Password successfully changed")
