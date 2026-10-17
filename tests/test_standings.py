import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import database
from app.importer import Importer, StandingsNotUpdatedError
from app.jolpica import UpstreamDataError
from app.main import app
from app.models import ConstructorStanding, DriverStanding, RaceResult
from tests.fixtures.jolpica.client import FixtureJolpicaClient
from tests.test_importer import FakeJolpica


def test_2024_standings_match_the_official_championship_including_sprints(sqlite_engine):
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


def test_excluded_constructors_have_no_position_and_are_listed_last(sqlite_engine):
    with database.SessionLocal() as session:
        Importer(session, ExcludedConstructorJolpica()).import_season(2024)

    with TestClient(app) as client:
        constructors = client.get("/seasons/2024/standings/constructors").json()

    assert [(c["id"], c["position"], c["position_text"]) for c in constructors] == [
        ("test-team", 1, "1"),
        ("excluded-team", None, "E"),
    ]


class FailingStandingsJolpica(FakeJolpica):
    def driver_standings(self, season):
        raise UpstreamDataError("Jolpica standings total changed during pagination")


class LaterRoundStandingsJolpica(FakeJolpica):
    def driver_standings(self, season):
        table = super().driver_standings(season)
        return {**table, "round": 2}


class EmptyStandingsJolpica(FakeJolpica):
    def driver_standings(self, season):
        return {"round": None, "standings": []}

    def constructor_standings(self, season):
        return {"round": None, "standings": []}


def count(session, model):
    return session.scalar(select(func.count()).select_from(model))


def test_standings_failure_keeps_results_and_flags_the_run(sqlite_engine):
    with database.SessionLocal() as session:
        with pytest.raises(StandingsNotUpdatedError, match="could not be fetched") as error:
            Importer(session, FailingStandingsJolpica()).import_season(2024)
        assert error.value.counts["results"] == 1
        assert count(session, RaceResult) == 1
        assert count(session, DriverStanding) == 0


def test_standings_from_another_round_are_not_stored(sqlite_engine):
    with database.SessionLocal() as session:
        with pytest.raises(StandingsNotUpdatedError, match="round 2, but results go to round 1"):
            Importer(session, LaterRoundStandingsJolpica()).import_season(2024)
        assert count(session, RaceResult) == 1
        assert count(session, DriverStanding) == 0


def test_empty_upstream_standings_keep_the_stored_ones(sqlite_engine):
    with database.SessionLocal() as session:
        Importer(session, FakeJolpica()).import_season(2024)
        with pytest.raises(StandingsNotUpdatedError, match="kept the stored ones"):
            Importer(session, EmptyStandingsJolpica()).import_season(2024)
        assert count(session, DriverStanding) == 1
        assert count(session, ConstructorStanding) == 1


def test_seasons_without_standings_import_cleanly(sqlite_engine):
    """Early seasons have no constructors' championship upstream; that is not an error."""
    with database.SessionLocal() as session:
        counts = Importer(session, EmptyStandingsJolpica()).import_season(2024)
    assert counts["results"] == 1
    assert counts["constructor_standings"] == 0
