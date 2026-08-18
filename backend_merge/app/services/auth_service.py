from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.login_log import LoginLog, LoginMethod
from app.models.user import AuthProvider, User
from app.schemas.auth_schema import SignupRequest
from app.security import decode_access_token, hash_password, verify_password
from app.services.google_oauth import GoogleTokenInvalid, verify_google_token

security = HTTPBearer(auto_error=False)


def create_local_user(db: Session, data: SignupRequest) -> User:
    """Signup - username ya email pehle se ho to 409 conflict."""
    existing = db.query(User).filter(
        or_(User.email == data.email, User.username == data.username)
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email already registered",
        )

    user = User(
        username=data.username,
        email=data.email,
        full_name=data.full_name,
        hashed_password=hash_password(data.password),
        auth_provider=AuthProvider.LOCAL,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_local_user(db: Session, email: str, password: str) -> User:
    """Email + password se login. Invalid ho to 401, disabled ho to 403."""
    user = db.query(User).filter(User.email == email).first()
    if not user or not user.hashed_password or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")
    return user


def get_or_create_google_user(db: Session, google_token: str) -> User:
    """Google id_token se user dhundhta/banata hai (team member wala design)."""
    try:
        info = verify_google_token(google_token)
    except GoogleTokenInvalid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Google token")

    user = db.query(User).filter(
        or_(User.google_id == info["google_id"], User.email == info["email"])
    ).first()

    if user:
        if not user.google_id:
            user.google_id = info["google_id"]
        db.commit()
        db.refresh(user)
        return user

    # username email ke prefix se banao; conflict ho to suffix lagao
    base_username = info["email"].split("@")[0]
    username = base_username
    suffix = 1
    while db.query(User).filter(User.username == username).first():
        username = f"{base_username}{suffix}"
        suffix += 1

    user = User(
        username=username,
        email=info["email"],
        full_name=info.get("full_name"),
        hashed_password=None,
        auth_provider=AuthProvider.GOOGLE,
        google_id=info["google_id"],
        is_verified=info.get("email_verified", False),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def log_login(
    db: Session,
    user: User,
    method: LoginMethod,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    """Har login ka audit record login_logs me save karta hai."""
    log_entry = LoginLog(
        user_id=user.id,
        login_method=method,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(log_entry)
    db.commit()


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI dependency - Bearer token se current user. Protected routes me use karo."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Login karke Authorization header me token bhejein.",
        )

    try:
        payload = decode_access_token(credentials.credentials)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    try:
        user = db.query(User).filter(User.id == int(user_id)).first()
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    return user
