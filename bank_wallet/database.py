from config import settings
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

DATABASE_URL = (
    f"postgresql+asyncpg://"
    f"{settings.WALLET_DB_USER}:{settings.WALLET_DB_PASSWORD}"
    f"@localhost:54312/{settings.WALLET_DB_NAME}"
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