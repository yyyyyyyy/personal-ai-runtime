"""Alembic environment config — uses project Settings for SQLite path."""

import os
import sys
from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context

# Ensure backend/ is on sys.path so we can import app.config
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("LLM_API_KEY", "alembic-migration-key")

from app.config import settings  # noqa: E402

# Alembic Config object
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Use the project's SQLite path
DB_URL = f"sqlite:///{settings.sqlite_path}"


def run_migrations_offline() -> None:
    url = DB_URL
    context.configure(url=url, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(DB_URL, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
