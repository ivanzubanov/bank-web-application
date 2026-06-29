from bank_auth.config import settings
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import (
    create_async_engine, async_sessionmaker, AsyncSession
)

DATABASE_URL = (
    f"postgresql+asyncpg://"
    f"{settings.AUTH_DB_USER}:{settings.AUTH_DB_PASSWORD}"
    f"@{settings.AUTH_DB_HOST}:{settings.AUTH_DB_PORT}/{settings.AUTH_DB_NAME}"
)

db_engine = create_async_engine(DATABASE_URL, echo=True)

AsyncSessionLocal = async_sessionmaker(
    bind=db_engine,
    class_=AsyncSession,
    expire_on_commit=False
)

class Base(DeclarativeBase):
    pass

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session