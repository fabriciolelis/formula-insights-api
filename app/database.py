"""Database engine, session factory, and schema creation."""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    """Declarative base class for all ORM models."""


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


def create_schema() -> None:
    """Create any missing tables; existing tables are left unchanged."""
    Base.metadata.create_all(engine)
