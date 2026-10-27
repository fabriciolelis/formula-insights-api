import logging

import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app import cli
from app.database import SchemaNotReadyError, ensure_schema_ready
from app.main import app
from app.models import Base
from tests.migrations import stamp, upgrade


@pytest.fixture
def empty_engine(bind_database):
    """In-memory SQLite database with no tables and no migrations, bound to the app."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    bind_database(engine)
    yield engine
    engine.dispose()


def test_migrations_match_the_models(empty_engine):
    upgrade(empty_engine)

    with empty_engine.connect() as connection:
        differences = compare_metadata(MigrationContext.configure(connection), Base.metadata)

    assert differences == [], "the models changed without a migration: run alembic revision"


def test_schema_at_head_is_ready(empty_engine):
    upgrade(empty_engine)

    ensure_schema_ready(empty_engine)


def test_database_without_migrations_is_not_ready(empty_engine):
    with pytest.raises(SchemaNotReadyError, match="no migrations applied"):
        ensure_schema_ready(empty_engine)


def test_database_behind_this_version_is_not_ready(empty_engine, monkeypatch):
    upgrade(empty_engine)
    # Simulate a newer release of the code whose latest migration is not applied yet.
    monkeypatch.setattr(ScriptDirectory, "get_current_head", lambda self: "0002")

    with pytest.raises(SchemaNotReadyError, match="at migration 0001; this version needs 0002"):
        ensure_schema_ready(empty_engine)


def test_database_newer_than_this_version_is_accepted(empty_engine, caplog):
    # After a rollback, the previous release runs on a schema migrated by the next one.
    upgrade(empty_engine)
    with empty_engine.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num = 'from_a_newer_release'"))

    with caplog.at_level(logging.WARNING, logger="app.database"):
        ensure_schema_ready(empty_engine)

    assert "newer than this version's 0001" in caplog.text


def test_api_refuses_to_start_on_an_unmigrated_database(empty_engine):
    with pytest.raises(SchemaNotReadyError), TestClient(app):
        pass


def test_import_does_not_start_on_an_unmigrated_database(empty_engine, capsys):
    Base.metadata.create_all(empty_engine)  # tables exist, but no migration was applied

    with pytest.raises(SystemExit) as exit_info:
        cli.main(["2024"])

    assert exit_info.value.code == 1
    assert capsys.readouterr().err.startswith(
        "Import not started: the database has no migrations applied"
    )


def test_stamped_database_is_ready(empty_engine):
    Base.metadata.create_all(empty_engine)
    stamp(empty_engine)

    ensure_schema_ready(empty_engine)
