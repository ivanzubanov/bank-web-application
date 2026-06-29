# migrations_wallet/env.py
import os
import sys
import asyncio
from logging.config import fileConfig

from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy import pool
from alembic import context

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from bank_wallet.config import settings
from bank_wallet.database import Base

alembic_config = context.config

if alembic_config.config_file_name is not None:
    fileConfig(alembic_config.config_file_name)

target_metadata = Base.metadata

cmd_line_url = alembic_config.get_main_option("sqlalchemy.url")

if not cmd_line_url or "placeholder" in cmd_line_url or "user:pass" in cmd_line_url:
    DATABASE_URL = (
        f"postgresql+asyncpg://"
        f"{settings.WALLET_DB_USER}:{settings.WALLET_DB_PASSWORD}"
        f"@{getattr(settings, 'WALLET_DB_HOST', 'localhost')}:{getattr(settings, 'WALLET_DB_PORT', 54312)}/{settings.WALLET_DB_NAME}"
    )
    alembic_config.set_main_option("sqlalchemy.url", DATABASE_URL)


def run_migrations_offline() -> None:
    url = alembic_config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        alembic_config.get_section(alembic_config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())