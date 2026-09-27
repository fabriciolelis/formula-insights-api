import os
from copy import deepcopy

import httpx


class UpstreamDataError(RuntimeError):
    """Raised when Jolpica returns an incomplete or inconsistent result set."""


class JolpicaClient:
    """Small client for the Jolpica Ergast-compatible historical API."""

    PAGE_SIZE = 100

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or os.getenv("JOLPICA_BASE_URL", "https://api.jolpi.ca/ergast/f1")

    def races(self, season: int) -> list[dict]:
        return self._paginate_races(f"{season}/races.json")

    def results(self, season: int) -> list[dict]:
        path = f"{season}/results.json"
        offset = 0
        expected_total: int | None = None
        received = 0
        races_by_round: dict[str, dict] = {}

        while expected_total is None or received < expected_total:
            payload = self._get(path, {"limit": self.PAGE_SIZE, "offset": offset})
            metadata = payload["MRData"]
            page_total = int(metadata["total"])
            if expected_total is None:
                expected_total = page_total
            elif page_total != expected_total:
                raise UpstreamDataError("Jolpica result total changed during pagination")

            races = metadata["RaceTable"]["Races"]
            page_results = sum(len(race["Results"]) for race in races)
            if page_results == 0:
                raise UpstreamDataError(
                    f"Jolpica returned an empty result page at offset {offset} before {expected_total} rows"
                )

            for race in races:
                stored_race = races_by_round.setdefault(
                    race["round"],
                    {key: deepcopy(value) for key, value in race.items() if key != "Results"} | {"Results": []},
                )
                stored_race["Results"].extend(deepcopy(race["Results"]))

            received += page_results
            if received > expected_total:
                raise UpstreamDataError(
                    f"Jolpica returned {received} results although its total is {expected_total}"
                )
            offset += page_results

        if received != expected_total:
            raise UpstreamDataError(
                f"Jolpica returned {received} results although its total is {expected_total}"
            )
        return [races_by_round[round_number] for round_number in sorted(races_by_round, key=int)]

    def _paginate_races(self, path: str) -> list[dict]:
        offset = 0
        expected_total: int | None = None
        races: list[dict] = []

        while expected_total is None or len(races) < expected_total:
            payload = self._get(path, {"limit": self.PAGE_SIZE, "offset": offset})
            metadata = payload["MRData"]
            page_total = int(metadata["total"])
            if expected_total is None:
                expected_total = page_total
            elif page_total != expected_total:
                raise UpstreamDataError("Jolpica race total changed during pagination")

            page_races = metadata["RaceTable"]["Races"]
            if not page_races:
                raise UpstreamDataError(
                    f"Jolpica returned an empty race page at offset {offset} before {expected_total} rows"
                )
            races.extend(deepcopy(page_races))
            if len(races) > expected_total:
                raise UpstreamDataError(
                    f"Jolpica returned {len(races)} races although its total is {expected_total}"
                )
            offset += len(page_races)

        return races

    def _get(self, path: str, params: dict[str, int]) -> dict:
        headers = {"User-Agent": "formula-insights-api/0.1 (portfolio project)"}
        with httpx.Client(timeout=30, headers=headers) as client:
            response = client.get(f"{self.base_url}/{path}", params=params)
            response.raise_for_status()
            return response.json()
