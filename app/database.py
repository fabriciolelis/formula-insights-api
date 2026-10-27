"""Database engine, session factory, and schema version check."""

import logging
import os
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

logger = logging.getLogger(__name__)

# Predictable constraint names, so migrations can refer to them (ADR-007).
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


class Base(DeclarativeBase):
    """Declarative base class for all ORM models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class SchemaNotReadyError(RuntimeError):
    """Raised when the database schema is missing or older than this code needs."""


def database_url() -> str:
    """Return the database URL from `DATABASE_URL`, defaulting to the local Compose database.

    Returns:
        A SQLAlchemy connection URL.
    """
    return os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://formula_insights:formula_insights@localhost:5432/formula_insights",
    )


engine = create_engine(database_url(), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def migration_script() -> ScriptDirectory:
    """Return the migration scripts shipped with this version of the code."""
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    return ScriptDirectory.from_config(config)


def ensure_schema_ready(bind: Engine | None = None) -> None:
    """Check that the database schema is at least as new as this code needs.

    Migrations are applied by a separate step (`alembic upgrade head`), never
    by the API or the importer (ADR-007). A database newer than this code is
    accepted, because expand-then-contract migrations keep the previous release
    working during a rollout or after a rollback.

    Args:
        bind: Engine to check; defaults to the application engine.

    Raises:
        SchemaNotReadyError: If no migration was applied, or the database is
            at an older migration than this code's latest one.
    """
    script = migration_script()
    head = script.get_current_head()
    with (bind or engine).connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()

    if current == head:
        return
    if current is None:
        raise SchemaNotReadyError(
            f"the database has no migrations applied; this version needs {head}. "
            "Run `alembic upgrade head`."
        )
    if current in {revision.revision for revision in script.walk_revisions()}:
        raise SchemaNotReadyError(
            f"the database is at migration {current}; this version needs {head}. "
            "Run `alembic upgrade head`."
        )
    logger.warning(
        "Database is at migration %s, which is newer than this version's %s; "
        "continuing, as migrations stay compatible with the previous release.",
        current,
        head,
    )
