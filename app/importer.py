"""Idempotent import of a Formula 1 season from Jolpica into the database."""

from datetime import date

import httpx
from sqlalchemy import delete, exists, select
from sqlalchemy.orm import Session

from app.jolpica import JolpicaClient, UpstreamDataError
from app.models import (
    Constructor,
    ConstructorStanding,
    Driver,
    DriverStanding,
    Race,
    RaceResult,
)


class StandingsNotUpdatedError(RuntimeError):
    """Races and results were saved, but the stored standings were kept unchanged.

    Args:
        counts: New rows per entity that were saved before standings failed.
        reason: Why the standings were not updated.

    Attributes:
        counts: New rows per entity that were saved before standings failed.
    """

    def __init__(self, counts: dict[str, int], reason: str) -> None:
        super().__init__(reason)
        self.counts = counts


class Importer:
    """Imports a season idempotently: re-running it updates rows instead of duplicating them.

    Args:
        session: Database session the import writes to.
        client: Source of Jolpica data (a fixture client in tests).
    """

    def __init__(self, session: Session, client: JolpicaClient) -> None:
        self.session = session
        self.client = client

    def import_season(self, season: int) -> dict[str, int]:
        """Import races, results, and official standings for one season.

        Races and results are committed first. Standings replace the stored
        ones only when they are complete and from the same round as the latest
        results; otherwise the stored standings are kept (ADR-006).

        Args:
            season: Championship year.

        Returns:
            New rows per entity: `races`, `results`, `driver_standings`, and
            `constructor_standings`. Updated rows are not counted.

        Raises:
            StandingsNotUpdatedError: If races and results were saved but the
                standings could not be fetched, came from another round, or
                were empty although standings were already stored.
            UpstreamDataError: If races or results are incomplete; nothing is saved.
            httpx.HTTPError: If fetching races or results fails; nothing is saved.
        """
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

        # Results are saved even if the standings below cannot be updated.
        self.session.commit()

        latest_round = max((int(item["round"]) for item in results if item["Results"]), default=None)
        try:
            driver_table = self.client.driver_standings(season)
            constructor_table = self.client.constructor_standings(season)
        except (UpstreamDataError, httpx.HTTPError) as error:
            raise StandingsNotUpdatedError(counts, f"standings could not be fetched: {error}") from error

        for name, model, table in (
            ("driver", DriverStanding, driver_table),
            ("constructor", ConstructorStanding, constructor_table),
        ):
            if table["standings"] and table["round"] != latest_round:
                raise StandingsNotUpdatedError(
                    counts,
                    f"{name} standings are for round {table['round']}, "
                    f"but results go to round {latest_round}",
                )
            if not table["standings"] and self._has_standings(model, season):
                raise StandingsNotUpdatedError(
                    counts, f"upstream returned no {name} standings; kept the stored ones"
                )

        counts["driver_standings"] = self._import_driver_standings(season, driver_table)
        counts["constructor_standings"] = self._import_constructor_standings(
            season, constructor_table
        )
        self.session.commit()
        return counts

    def _has_standings(self, model: type[DriverStanding | ConstructorStanding], season: int) -> bool:
        return bool(self.session.scalar(select(exists().where(model.season == season))))

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

    def _import_driver_standings(self, season: int, table: dict) -> int:
        """Upsert driver standings and delete rows no longer published upstream."""
        if not table["standings"]:
            return 0
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

    def _import_constructor_standings(self, season: int, table: dict) -> int:
        """Upsert constructor standings and delete rows no longer published upstream."""
        if not table["standings"]:
            return 0
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
        """Copy one standings row; entries without a numeric position (excluded) get None."""
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
