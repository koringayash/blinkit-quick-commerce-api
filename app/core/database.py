from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import DATABASE_URL

# echo stays off: SQL logging is controlled via the "sqlalchemy.engine" logger (DB_ECHO)
# so statements flow through the structured JSON logger instead of a separate raw handler.
# pool_pre_ping transparently replaces connections dropped by Postgres/proxies.
engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
