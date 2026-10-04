from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.sdk.database import get_db
from src.domains.auth.models import AuthProvider, LoginLog, LoginMethod, User
from src.domains.auth.schemas import SignupRequest
from src.domains.security.jwt import decode_access_token, hash_password, verify_password
from src.domains.auth.google_oauth import GoogleTokenInvalid, verify_google_token

security = HTTPBearer(auto_error=False)


async def _unique_username(db: AsyncSession, base_username: str) -> str:
    """Base se shuru ho kar pehla unused username dhundhta hai."""
    base = "".join(c for c in base_username if c.isalnum() or c in "._-")[:40] or "user"
    if len(base) < 3:
        base = f"{base}user"
    username = base
    suffix = 1
    while True:
        res = await db.execute(select(User).where(User.username == username))
        if not res.scalars().first():
            return username
        username = f"{base}{suffix}"
        suffix += 1


async def create_local_user(db: AsyncSession, data: SignupRequest) -> User:
    """Signup - username ya email pehle se ho to 409 conflict."""
    conditions = [User.email == data.email]
    if data.username:
        conditions.append(User.username == data.username)
    res = await db.execute(select(User).where(or_(*conditions)))
    existing = res.scalars().first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email already registered",
        )

    username = data.username or await _unique_username(db, data.email.split("@")[0])
    user = User(
        username=username,
        email=data.email,
        full_name=data.full_name,
        hashed_password=hash_password(data.password),
        auth_provider=AuthProvider.LOCAL,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate_local_user(db: AsyncSession, email: str, password: str) -> User:
    """Email + password se login. Invalid ho to 401, disabled ho to 403."""
    stmt = select(User).where(User.email == email)
    res = await db.execute(stmt)
    user = res.scalars().first()

    if not user or not user.hashed_password or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")
    return user


async def get_or_create_google_user(db: AsyncSession, google_token: str) -> User:
    """Google id_token se user dhundhta/banata hai."""
    try:
        info = verify_google_token(google_token)
    except GoogleTokenInvalid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Google token")

    stmt = select(User).where(or_(User.google_id == info["google_id"], User.email == info["email"]))
    res = await db.execute(stmt)
    user = res.scalars().first()

    if user:
        if not user.google_id:
            user.google_id = info["google_id"]
        await db.commit()
        await db.refresh(user)
        return user

    username = await _unique_username(db, info["email"].split("@")[0])

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
    await db.commit()
    await db.refresh(user)
    return user


async def log_login(
    db: AsyncSession,
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
    await db.commit()


async def get_optional_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """Optional auth dependency.

    No token -> guest user (None).
    Valid token -> current user.
    Invalid token -> treated as unauthenticated guest.
    """
    if credentials is None:
        return None

    try:
        payload = decode_access_token(credentials.credentials)
    except ValueError:
        return None

    user_id = payload.get("sub")
    if user_id is None:
        return None

    try:
        stmt = select(User).where(User.id == int(user_id))
        res = await db.execute(stmt)
        user = res.scalars().first()
    except (TypeError, ValueError):
        return None

    if user is None or not user.is_active:
        return None

    return user

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """FastAPI dependency - Bearer token se current user."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Please log in and provide a Bearer token.",
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
        stmt = select(User).where(User.id == int(user_id))
        res = await db.execute(stmt)
        user = res.scalars().first()
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    return user

