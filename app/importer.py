from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jolpica import JolpicaClient
from app.models import Constructor, Driver, Race, RaceResult


class Importer:
    def __init__(self, session: Session, client: JolpicaClient) -> None:
        self.session = session
        self.client = client

    def import_season(self, season: int) -> dict[str, int]:
        races = {int(race["round"]): race for race in self.client.races(season)}
        results = self.client.results(season)
        counts = {"races": 0, "results": 0}

        for round_number, payload in races.items():
            race, created = self._upsert_race(season, round_number, payload)
            counts["races"] += created
            result_payload = next(
                (item for item in results if int(item["round"]) == round_number), {"Results": []}
            )
            for result in result_payload["Results"]:
                counts["results"] += self._upsert_result(race, result)

        self.session.commit()
        return counts

    def _upsert_race(self, season: int, round_number: int, payload: dict) -> tuple[Race, int]:
        race = self.session.scalar(select(Race).where(Race.season == season, Race.round == round_number))
        created = int(race is None)
        race = race or Race(season=season, round=round_number)
        circuit = payload["Circuit"]
        race.name = payload["raceName"]
        race.race_date = date.fromisoformat(payload["date"])
        race.circuit_id = circuit["circuitId"]
        race.circuit_name = circuit["circuitName"]
        self.session.add(race)
        self.session.flush()
        return race, created

    def _upsert_result(self, race: Race, payload: dict) -> int:
        driver_payload, constructor_payload = payload["Driver"], payload["Constructor"]
        driver = self.session.get(Driver, driver_payload["driverId"])
        if driver is None:
            driver = Driver(
                id=driver_payload["driverId"],
                given_name=driver_payload["givenName"],
                family_name=driver_payload["familyName"],
                nationality=driver_payload.get("nationality"),
            )
        constructor = self.session.get(Constructor, constructor_payload["constructorId"])
        if constructor is None:
            constructor = Constructor(
                id=constructor_payload["constructorId"],
                name=constructor_payload["name"],
                nationality=constructor_payload.get("nationality"),
            )
        self.session.add_all([driver, constructor])
        self.session.flush()
        result = self.session.scalar(
            select(RaceResult).where(RaceResult.race_id == race.id, RaceResult.driver_id == driver.id)
        )
        created = int(result is None)
        result = result or RaceResult(race_id=race.id, driver_id=driver.id, constructor_id=constructor.id)
        result.constructor_id = constructor.id
        result.position = int(payload["position"]) if payload["position"].isdigit() else None
        result.position_text = payload["positionText"]
        result.points = float(payload["points"])
        result.status = payload["status"]
        self.session.add(result)
        return created
