"""Password hashing and JWT creation/decoding (no FastAPI/DB dependencies)."""
import asyncio
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import bcrypt
import jwt

from app.core.config import ACCESS_TOKEN_EXPIRE_MINUTES, JWT_ALGORITHM, JWT_SECRET


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    # bcrypt works on bytes; the hash is stored as str in the DB, so encode it back.
    return bcrypt.checkpw(password.encode(), hashed.encode())


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    return hash_password("timing-equalizer-not-a-real-password")


# bcrypt is deliberately slow (~250ms) and CPU-bound. Running it directly inside an async
# endpoint blocks the event loop and stalls every other request, so offload to a thread.
async def hash_password_async(password: str) -> str:
    return await asyncio.to_thread(hash_password, password)


async def verify_password_async(password: str, hashed: str | None) -> bool:
    """
    Verify a password off the event loop. When the user doesn't exist (hashed=None) we still
    run a bcrypt check against a dummy hash so response timing doesn't reveal which emails exist.
    """
    if hashed is None:
        await asyncio.to_thread(lambda: verify_password(password, _dummy_hash()))
        return False
    return await asyncio.to_thread(verify_password, password, hashed)


def create_access_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": str(user_id), "exp": expire}, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> int:
    """Return the user id from a token. Raises jwt.PyJWTError / KeyError / ValueError if invalid."""
    payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    return int(payload["sub"])
