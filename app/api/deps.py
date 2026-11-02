"""Shared FastAPI dependencies (current user, SSE token fallback, admin guard)."""
import jwt
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models import User

# tokenUrl powers the "Authorize" button in Swagger UI (/docs)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


async def _resolve_user_from_token(raw_token: str | None, db: AsyncSession) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not raw_token:
        raise credentials_error
    try:
        user_id = decode_access_token(raw_token)
    except (jwt.PyJWTError, KeyError, ValueError):
        raise credentials_error

    user = await db.get(User, user_id)
    if user is None:
        raise credentials_error
    return user


async def get_current_user(
    token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)
) -> User:
    return await _resolve_user_from_token(token, db)


async def get_current_user_sse(
    header_token: str | None = Depends(oauth2_scheme_optional),
    query_token: str | None = Query(None, alias="token", description="JWT token for browser EventSource SSE connections"),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Authenticate via Authorization Bearer header OR `?token=` query param (required for browser EventSource)."""
    return await _resolve_user_from_token(header_token or query_token, db)


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user
