from fastapi import HTTPException, status, Request
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
from sqlalchemy import insert

from app.models import RegisteredStudent, LoginUser, AuthProvider, LoginMethod
from app.schemas import SignupRequest
from app.security import hash_password, verify_password
from app.auth.google_oauth import verify_google_token, GoogleTokenInvalid


async def create_local_user(db: AsyncSession, data: SignupRequest) -> RegisteredStudent:
    existing = await db.execute(
        select(RegisteredStudent).where(
            or_(RegisteredStudent.email == data.email, RegisteredStudent.username == data.username)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username or email already registered")

    user = RegisteredStudent(
        username=data.username,
        email=data.email,
        full_name=data.full_name,
        hashed_password=hash_password(data.password),
        auth_provider=AuthProvider.LOCAL,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate_local_user(db: AsyncSession, email: str, password: str) -> RegisteredStudent:
    result = await db.execute(select(RegisteredStudent).where(RegisteredStudent.email == email))
    user = result.scalar_one_or_none()

    if not user or not user.hashed_password or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")

    return user


async def get_or_create_google_user(db: AsyncSession, google_token: str) -> RegisteredStudent:
    try:
        info = verify_google_token(google_token)
    except GoogleTokenInvalid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Google token")

    result = await db.execute(
        select(RegisteredStudent).where(
            or_(RegisteredStudent.google_id == info["google_id"], RegisteredStudent.email == info["email"])
        )
    )
    user = result.scalar_one_or_none()

    if user:
        if not user.google_id:
            user.google_id = info["google_id"]
            await db.commit()
            await db.refresh(user)
        return user

    base_username = info["email"].split("@")[0]
    username = base_username
    suffix = 1
    while (
        await db.execute(select(RegisteredStudent).where(RegisteredStudent.username == username))
    ).scalar_one_or_none():
        username = f"{base_username}{suffix}"
        suffix += 1

    user = RegisteredStudent(
        username=username,
        email=info["email"],
        full_name=info.get("full_name"),
        hashed_password=None,
        auth_provider=AuthProvider.GOOGLE,
        google_id=info["google_id"],
        is_verified=info.get("email_verified", False),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def log_login(db: AsyncSession, user: RegisteredStudent, method: LoginMethod, request: Request) -> None:
    expires_at = datetime.utcnow() + timedelta(hours=24)
    stmt = insert(LoginUser).values(
        student_id=user.id,
        login_method=method,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        session_token_expires_at=expires_at,
    )
    await db.execute(stmt)
    await db.commit()
