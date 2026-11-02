"""Registration and login."""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import ADMIN_EMAILS
from app.core.database import get_db
from app.core.logging import get_logger
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.schemas.user import TokenResponse, UserRegister, UserResponse

logger = get_logger("app.auth")
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: UserRegister, db: AsyncSession = Depends(get_db)):
    email = payload.email.lower()
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        is_admin=email in ADMIN_EMAILS,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    logger.info(
        f"User registered: {user.email} (id: {user.id}, admin: {user.is_admin})",
        extra={"user_id": user.id, "email": user.email, "is_admin": user.is_admin},
    )
    return user


@router.post("/login", response_model=TokenResponse)
async def login(form: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    """OAuth2 form login. Put your email in the `username` field."""
    result = await db.execute(select(User).where(User.email == form.username.lower()))
    user = result.scalar_one_or_none()
    if not user or not verify_password(form.password, user.hashed_password):
        logger.warning(
            f"Failed login attempt for email: {form.username.lower()}",
            extra={"email": form.username.lower()},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    logger.info(f"User logged in: {user.email} (id: {user.id})", extra={"user_id": user.id, "email": user.email})
    return TokenResponse(access_token=create_access_token(user.id))
