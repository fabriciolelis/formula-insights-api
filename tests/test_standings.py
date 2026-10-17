from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app import database
from app.importer import Importer
from app.main import app
from app.models import Base
from tests.fixtures.jolpica.client import FixtureJolpicaClient
from tests.test_importer import FakeJolpica


def use_sqlite_engine():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    database.engine = engine
    database.SessionLocal.configure(bind=engine)
    Base.metadata.create_all(engine)


def test_2024_standings_match_the_official_championship_including_sprints():
    use_sqlite_engine()
    with database.SessionLocal() as session:
        counts = Importer(session, FixtureJolpicaClient()).import_season(2024)
    assert counts["driver_standings"] == 24
    assert counts["constructor_standings"] == 10

    with TestClient(app) as client:
        drivers = client.get("/seasons/2024/standings/drivers").json()
        constructors = client.get("/seasons/2024/standings/constructors").json()

    assert [(d["position"], d["id"], d["points"]) for d in drivers[:2]] == [
        (1, "max_verstappen", 437),
        (2, "norris", 374),
    ]
    assert drivers[0]["wins"] == 9
    assert [(c["position"], c["id"], c["points"]) for c in constructors[:2]] == [
        (1, "mclaren", 666),
        (2, "ferrari", 652),
    ]


class ExcludedConstructorJolpica(FakeJolpica):
    """Mirrors how Jolpica reports an excluded team, e.g. McLaren in 2007."""

    def constructor_standings(self, season):
        team = {"constructorId": "test-team", "name": "Test Team", "nationality": "Test"}
        excluded = {"constructorId": "excluded-team", "name": "Excluded", "nationality": "Test"}
        return {
            "round": 1,
            "standings": [
                {"positionText": "E", "points": "0", "wins": "0", "Constructor": excluded},
                {"position": "1", "positionText": "1", "points": "25", "wins": "1", "Constructor": team},
            ],
        }


def test_excluded_constructors_have_no_position_and_are_listed_last():
    use_sqlite_engine()
    with database.SessionLocal() as session:
        Importer(session, ExcludedConstructorJolpica()).import_season(2024)

    with TestClient(app) as client:
        constructors = client.get("/seasons/2024/standings/constructors").json()

    assert [(c["id"], c["position"], c["position_text"]) for c in constructors] == [
        ("test-team", 1, "1"),
        ("excluded-team", None, "E"),
    ]
