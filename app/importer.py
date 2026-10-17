from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.jolpica import JolpicaClient
from app.models import (
    Constructor,
    ConstructorStanding,
    Driver,
    DriverStanding,
    Race,
    RaceResult,
)


class Importer:
    def __init__(self, session: Session, client: JolpicaClient) -> None:
        self.session = session
        self.client = client

    def import_season(self, season: int) -> dict[str, int]:
        races = {int(race["round"]): race for race in self.client.races(season)}
        results = self.client.results(season)
        counts = {"races": 0, "results": 0, "driver_standings": 0, "constructor_standings": 0}

        for round_number, payload in races.items():
            race, created = self._upsert_race(season, round_number, payload)
            counts["races"] += created
            result_payload = next(
                (item for item in results if int(item["round"]) == round_number), {"Results": []}
            )
            for result in result_payload["Results"]:
                counts["results"] += self._upsert_result(race, result)

        counts["driver_standings"] = self._import_driver_standings(season)
        counts["constructor_standings"] = self._import_constructor_standings(season)

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
        driver = self._driver(payload["Driver"])
        constructor = self._constructor(payload["Constructor"])
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

    def _import_driver_standings(self, season: int) -> int:
        table = self.client.driver_standings(season)
        created = 0
        driver_ids = []
        for payload in table["standings"]:
            driver = self._driver(payload["Driver"])
            driver_ids.append(driver.id)
            standing = self.session.scalar(
                select(DriverStanding).where(
                    DriverStanding.season == season, DriverStanding.driver_id == driver.id
                )
            )
            created += int(standing is None)
            standing = standing or DriverStanding(season=season, driver_id=driver.id)
            self._apply_standing(standing, table["round"], payload)
            self.session.add(standing)
        self.session.execute(
            delete(DriverStanding).where(
                DriverStanding.season == season, DriverStanding.driver_id.not_in(driver_ids)
            )
        )
        return created

    def _import_constructor_standings(self, season: int) -> int:
        table = self.client.constructor_standings(season)
        created = 0
        constructor_ids = []
        for payload in table["standings"]:
            constructor = self._constructor(payload["Constructor"])
            constructor_ids.append(constructor.id)
            standing = self.session.scalar(
                select(ConstructorStanding).where(
                    ConstructorStanding.season == season,
                    ConstructorStanding.constructor_id == constructor.id,
                )
            )
            created += int(standing is None)
            standing = standing or ConstructorStanding(season=season, constructor_id=constructor.id)
            self._apply_standing(standing, table["round"], payload)
            self.session.add(standing)
        self.session.execute(
            delete(ConstructorStanding).where(
                ConstructorStanding.season == season,
                ConstructorStanding.constructor_id.not_in(constructor_ids),
            )
        )
        return created

    @staticmethod
    def _apply_standing(
        standing: DriverStanding | ConstructorStanding, round_number: int, payload: dict
    ) -> None:
        position = payload.get("position", "")
        standing.round = round_number
        standing.position = int(position) if position.isdigit() else None
        standing.position_text = payload["positionText"]
        standing.points = float(payload["points"])
        standing.wins = int(payload["wins"])

    def _driver(self, payload: dict) -> Driver:
        driver = self.session.get(Driver, payload["driverId"])
        if driver is None:
            driver = Driver(
                id=payload["driverId"],
                given_name=payload["givenName"],
                family_name=payload["familyName"],
                nationality=payload.get("nationality"),
            )
            self.session.add(driver)
            self.session.flush()
        return driver

    def _constructor(self, payload: dict) -> Constructor:
        constructor = self.session.get(Constructor, payload["constructorId"])
        if constructor is None:
            constructor = Constructor(
                id=payload["constructorId"],
                name=payload["name"],
                nationality=payload.get("nationality"),
            )
            self.session.add(constructor)
            self.session.flush()
        return constructor
