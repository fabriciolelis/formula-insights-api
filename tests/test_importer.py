from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.importer import Importer
from app.models import Race, RaceResult


class FakeJolpica:
    def races(self, season):
        return [{"round": "1", "raceName": "Test Grand Prix", "date": "2024-03-02",
                 "Circuit": {"circuitId": "test", "circuitName": "Test Circuit"}}]

    def results(self, season):
        return [{"round": "1", "Results": [{"number": "1", "position": "1", "positionText": "1", "points": "25",
                 "status": "Finished", "Driver": {"driverId": "test-driver", "givenName": "Test",
                 "familyName": "Driver", "nationality": "Test"}, "Constructor": {"constructorId": "test-team",
                 "name": "Test Team", "nationality": "Test"}}]}]

    def driver_standings(self, season):
        return {"round": 1, "standings": [{"position": "1", "positionText": "1", "points": "25",
                "wins": "1", "Driver": {"driverId": "test-driver", "givenName": "Test",
                "familyName": "Driver", "nationality": "Test"}}]}

    def constructor_standings(self, season):
        return {"round": 1, "standings": [{"position": "1", "positionText": "1", "points": "25",
                "wins": "1", "Constructor": {"constructorId": "test-team", "name": "Test Team",
                "nationality": "Test"}}]}


def test_import_is_idempotent():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    importer = Importer(session, FakeJolpica())

    assert importer.import_season(2024) == {
        "races": 1, "results": 1, "driver_standings": 1, "constructor_standings": 1
    }
    assert importer.import_season(2024) == {
        "races": 0, "results": 0, "driver_standings": 0, "constructor_standings": 0
    }
    assert session.scalar(select(func.count()).select_from(Race)) == 1
    assert session.scalar(select(func.count()).select_from(RaceResult)) == 1


class SharedDriveJolpica(FakeJolpica):
    """Like 1956 round 1: Fangio won in car 34 and retired in car 30."""

    def results(self, season):
        race = super().results(season)[0]
        win = race["Results"][0]
        retired = {**win, "number": "30", "position": "13", "positionText": "R", "points": "0",
                   "status": "Fuel pump"}
        return [{**race, "Results": [{**win, "number": "34"}, retired]}]


def test_a_driver_can_have_two_results_in_one_race():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    importer = Importer(session, SharedDriveJolpica())

    assert importer.import_season(1956)["results"] == 2
    assert importer.import_season(1956)["results"] == 0
    stored = session.scalars(select(RaceResult).order_by(RaceResult.position)).all()
    assert [(result.number, result.position_text) for result in stored] == [("34", "1"), ("30", "R")]
