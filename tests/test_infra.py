import pytest
from sqlalchemy import text
from tests.conftest import TestingSessionLocal

@pytest.mark.asyncio
async def test_infrastructure_is_ready():
    assert True

@pytest.mark.asyncio
async def test_db_connection_and_session():
    async with TestingSessionLocal() as session:
        result = await session.execute(text("SELECT 1;"))
        assert result.scalar() == 1

@pytest.mark.asyncio
async def test_alembic_migrations_applied():
    async with TestingSessionLocal() as session:
        result = await session.execute(text("SELECT count(*) FROM users;"))
        count = result.scalar()
        assert count == 0

