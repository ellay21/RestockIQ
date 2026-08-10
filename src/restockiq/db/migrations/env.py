"""
Alembic migration environment for RestockIQ.

  1. Imports all ORM models (via db.base.Base.metadata) so autogenerate
     can discover every table definition in one pass.
  2. Reads DATABASE_URL from the environment (falls back to alembic.ini).
  3. Supports both online (direct DB connection) and offline (SQL script) modes.
"""
from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Import all ORM models so their metadata is registered
# IMPORTANT: every orm_models.py must be imported here; otherwise Alembic
# won't detect new or removed tables during autogenerate.
from restockiq.db.base import Base

# Alembic Config object
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Use the shared declarative base metadata for autogenerate
target_metadata = Base.metadata


def get_url() -> str:
    """
    Return the database URL, preferring the DATABASE_URL env var.

    Alembic uses psycopg2 (sync) for migrations, so we strip the +asyncpg
    driver suffix if present.
    """
    default_url = "postgresql://restockiq:restockiq@localhost:5432/restockiq"
    url = os.getenv("DATABASE_URL") or config.get_main_option("sqlalchemy.url") or default_url
    # Normalise asyncpg URL -> sync psycopg2 URL for Alembic
    return url.replace("postgresql+asyncpg://", "postgresql://")


def run_migrations_offline() -> None:
    """
    Emit migration SQL to stdout without requiring a live DB connection.
    Useful for generating migration scripts for review/audit.
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect to the database and apply migrations directly."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
