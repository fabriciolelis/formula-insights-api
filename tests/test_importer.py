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
        return [{"round": "1", "Results": [{"position": "1", "positionText": "1", "points": "25",
                 "status": "Finished", "Driver": {"driverId": "test-driver", "givenName": "Test",
                 "familyName": "Driver", "nationality": "Test"}, "Constructor": {"constructorId": "test-team",
                 "name": "Test Team", "nationality": "Test"}}]}]


def test_import_is_idempotent():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    importer = Importer(session, FakeJolpica())

    assert importer.import_season(2024) == {"races": 1, "results": 1}
    assert importer.import_season(2024) == {"races": 0, "results": 0}
    assert session.scalar(select(func.count()).select_from(Race)) == 1
    assert session.scalar(select(func.count()).select_from(RaceResult)) == 1
