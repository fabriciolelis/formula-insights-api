import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text

from app import database
from app.importer import Importer
from app.main import app
from app.models import Base, Race, RaceResult
from tests.fixtures.jolpica.client import FixtureJolpicaClient

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
# GitHub Actions sets CI=true: there the test must run, so a missing URL fails instead of skipping.
RUNNING_IN_CI = os.getenv("CI") == "true"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not TEST_DATABASE_URL and not RUNNING_IN_CI, reason="TEST_DATABASE_URL is not set"
    ),
]


@pytest.fixture
def postgres_engine(bind_database):
    """Engine bound to a throwaway schema, so the test never touches existing tables."""
    if not TEST_DATABASE_URL:
        pytest.fail("TEST_DATABASE_URL must be set when running in CI")
    schema = f"test_{uuid.uuid4().hex[:12]}"
    admin = create_engine(TEST_DATABASE_URL)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(TEST_DATABASE_URL, connect_args={"options": f"-csearch_path={schema}"})
    Base.metadata.create_all(engine)
    bind_database(engine)
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def test_2024_season_import_is_complete_and_idempotent_on_postgres(postgres_engine):
    with database.SessionLocal() as session:
        importer = Importer(session, FixtureJolpicaClient())
        assert importer.import_season(2024) == {"races": 24, "results": 479}
        assert importer.import_season(2024) == {"races": 0, "results": 0}
        assert session.scalar(select(func.count()).select_from(Race)) == 24
        assert session.scalar(select(func.count()).select_from(RaceResult)) == 479

    with TestClient(app) as client:
        races = client.get("/seasons/2024/races").json()
        assert len(races) == 24
        assert races[0]["name"] == "Bahrain Grand Prix"
        results = client.get("/seasons/2024/races/1/results").json()
        assert len(results) == 20
        assert results[0]["driver"]["id"] == "max_verstappen"
