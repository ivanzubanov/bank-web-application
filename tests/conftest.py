import os
import pytest
import asyncio
import pytest_asyncio
from alembic.config import Config
from alembic import command
import asyncpg
from sqlalchemy import text, pool
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from httpx import AsyncClient, ASGITransport
from dotenv import load_dotenv

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from bank_auth.main import app as auth_app
from bank_auth.database import get_db
from bank_auth.config import settings as auth_settings
from bank_wallet.config import settings as wallet_settings

TEST_AUTH_DB_URL = f"postgresql+asyncpg://{auth_settings.AUTH_DB_USER}:{auth_settings.AUTH_DB_PASSWORD}@{auth_settings.AUTH_DB_HOST}:{auth_settings.AUTH_DB_PORT}/{auth_settings.AUTH_DB_NAME}_test"
TEST_WALLET_DB_URL = f"postgresql+asyncpg://{wallet_settings.WALLET_DB_USER}:{wallet_settings.WALLET_DB_PASSWORD}@{getattr(wallet_settings, 'WALLET_DB_HOST', 'localhost')}:{getattr(wallet_settings, 'WALLET_DB_PORT', 54312)}/{wallet_settings.WALLET_DB_NAME}_test"

async def create_test_database(db_user, db_pass, db_host, db_port, db_name):
    conn = await asyncpg.connect(user=db_user, password=db_pass, host=db_host, port=db_port, database="postgres")
    try:
        exists = await conn.fetchval(f"SELECT 1 FROM pg_database WHERE datname='{db_name}'")
        if not exists:
            await conn.execute(f"CREATE DATABASE {db_name}")
    finally:
        await conn.close()

async def clear_database_schema(db_user, db_pass, db_host, db_port, db_name):
    conn = await asyncpg.connect(user=db_user, password=db_pass, host=db_host, port=db_port, database=db_name)
    try:
        await conn.execute("DROP SCHEMA public CASCADE;")
        await conn.execute("CREATE SCHEMA public;")
    finally:
        await conn.close()


@pytest.fixture(scope="session", autouse=True)
def prepare_databases():
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(create_test_database(
            auth_settings.AUTH_DB_USER, auth_settings.AUTH_DB_PASSWORD,
            auth_settings.AUTH_DB_HOST, auth_settings.AUTH_DB_PORT, f"{auth_settings.AUTH_DB_NAME}_test"
        ))
        loop.run_until_complete(create_test_database(
            wallet_settings.WALLET_DB_USER, wallet_settings.WALLET_DB_PASSWORD,
            getattr(wallet_settings, 'WALLET_DB_HOST', 'localhost'), getattr(wallet_settings, 'WALLET_DB_PORT', 54312),
            f"{wallet_settings.WALLET_DB_NAME}_test"
        ))

        loop.run_until_complete(clear_database_schema(
            auth_settings.AUTH_DB_USER, auth_settings.AUTH_DB_PASSWORD,
            auth_settings.AUTH_DB_HOST, auth_settings.AUTH_DB_PORT, f"{auth_settings.AUTH_DB_NAME}_test"
        ))
        loop.run_until_complete(clear_database_schema(
            wallet_settings.WALLET_DB_USER, wallet_settings.WALLET_DB_PASSWORD,
            getattr(wallet_settings, 'WALLET_DB_HOST', 'localhost'), getattr(wallet_settings, 'WALLET_DB_PORT', 54312),
            f"{wallet_settings.WALLET_DB_NAME}_test"
        ))
    finally:
        loop.close()

    alembic_auth_cfg = Config(os.path.join(PROJECT_ROOT, "alembic_auth.ini"))
    alembic_auth_cfg.set_main_option("sqlalchemy.url", TEST_AUTH_DB_URL)
    command.upgrade(alembic_auth_cfg, "head")

    alembic_wallet_cfg = Config(os.path.join(PROJECT_ROOT, "alembic_wallet.ini"))
    alembic_wallet_cfg.set_main_option("sqlalchemy.url", TEST_WALLET_DB_URL)
    command.upgrade(alembic_wallet_cfg, "head")

    yield

@pytest.fixture(scope="session", autouse=True)
def disable_rate_limiter():
    yield

test_engine = create_async_engine(TEST_AUTH_DB_URL, echo=False, poolclass=pool.NullPool)
TestingSessionLocal = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)

async def override_get_db():
    async with TestingSessionLocal() as session:
        yield session

@pytest_asyncio.fixture(scope="function")
async def ac():
    auth_app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=auth_app), base_url="http://test") as client:
        yield client
    auth_app.dependency_overrides.clear()

@pytest_asyncio.fixture(scope="function", autouse=True)
async def clean_tables():
    async with test_engine.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE users CASCADE;"))
    yield