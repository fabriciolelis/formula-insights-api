import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app import database
from app.models import Base
from tests.migrations import stamp


@pytest.fixture
def bind_database():
    """Point the app's engine and session factory at a test engine, then restore them."""
    original_engine = database.engine
    original_bind = database.SessionLocal.kw.get("bind")

    def bind(engine) -> None:
        database.engine = engine
        database.SessionLocal.configure(bind=engine)

    yield bind
    database.engine = original_engine
    database.SessionLocal.configure(bind=original_bind)


@pytest.fixture
def sqlite_engine(bind_database):
    """In-memory SQLite database bound to the app for the duration of one test.

    Tables come from the models, and the database is marked as migrated, so
    unit tests stay fast; the migrations themselves are tested on PostgreSQL
    and against the models in test_migrations.py.
    """
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    stamp(engine)
    bind_database(engine)
    yield engine
    engine.dispose()
