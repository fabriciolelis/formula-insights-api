"""Client for the Jolpica F1 API (Ergast-compatible historical data)."""

import os
from copy import deepcopy

import httpx
from pyrate_limiter import Duration, Limiter, Rate

# ADR-006: stay under Jolpica's 4 requests/s burst and 500 requests/hour limits.
REQUEST_RATES = [Rate(1, Duration.SECOND), Rate(450, Duration.HOUR)]


def default_limiter() -> Limiter:
    """Return a limiter that paces requests as ADR-006 requires.

    Returns:
        An in-memory limiter allowing at most 1 request per second and 450 per
        rolling hour. It waits for capacity instead of failing.
    """
    return Limiter(REQUEST_RATES)


class UpstreamDataError(RuntimeError):
    """Raised when Jolpica returns an incomplete or inconsistent result set."""


class JolpicaClient:
    """Client for the Jolpica Ergast-compatible historical API.

    Every list endpoint is read with offset pagination, and the rows received
    must match the total Jolpica reports, so a season is never imported
    partially (ADR-006).

    Every request waits for the client's limiter, so all requests sent through
    one client share a single budget; use one client for a whole run, including
    a multi-season backfill. The client never retries: an HTTP error such as
    `429` is raised to the caller.

    Args:
        base_url: API root. Defaults to `JOLPICA_BASE_URL`, then the public
            Jolpica endpoint.
        limiter: Paces the requests. Defaults to `default_limiter()`.
    """

    PAGE_SIZE = 100

    def __init__(self, base_url: str | None = None, limiter: Limiter | None = None) -> None:
        self.base_url = base_url or os.getenv("JOLPICA_BASE_URL", "https://api.jolpi.ca/ergast/f1")
        self.limiter = limiter or default_limiter()

    def races(self, season: int) -> list[dict]:
        """Return every race of a season.

        Args:
            season: Championship year.

        Returns:
            Race payloads as published by Jolpica, including circuit details.

        Raises:
            UpstreamDataError: If pages are missing or totals are inconsistent.
            httpx.HTTPError: If a request fails.
        """
        return self._paginate_races(f"{season}/races.json")

    def results(self, season: int) -> list[dict]:
        """Return every Grand Prix result of a season, grouped by race.

        Results of a race can span several pages; they are merged so each race
        appears once, in round order.

        Args:
            season: Championship year.

        Returns:
            Race payloads, each with its complete `Results` list.

        Raises:
            UpstreamDataError: If pages are missing or the row count does not
                match the reported total.
            httpx.HTTPError: If a request fails.
        """
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
            if expected_total == 0:
                return []

            races = metadata["RaceTable"]["Races"]
            page_results = sum(len(race["Results"]) for race in races)
            if page_results == 0:
                raise UpstreamDataError(
                    f"Jolpica returned an empty result page at offset {offset} before {expected_total} rows"
                )

            for race in races:
                race_without_results = {
                    key: deepcopy(value) for key, value in race.items() if key != "Results"
                }
                stored_race = races_by_round.setdefault(
                    race["round"], {**race_without_results, "Results": []}
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

    def driver_standings(self, season: int) -> dict:
        """Return the official driver standings after the latest round.

        Args:
            season: Championship year.

        Returns:
            `{"round": int | None, "standings": [...]}`; the list is empty and
            the round is None when Jolpica has no standings for the season.

        Raises:
            UpstreamDataError: If pages are missing, totals change, or the round
                changes during pagination.
            httpx.HTTPError: If a request fails.
        """
        return self._paginate_standings(f"{season}/driverStandings.json", "DriverStandings")

    def constructor_standings(self, season: int) -> dict:
        """Return the official constructor standings after the latest round.

        Args:
            season: Championship year.

        Returns:
            `{"round": int | None, "standings": [...]}`; the list is empty and
            the round is None when Jolpica has no standings for the season
            (there was no constructors' championship before 1958).

        Raises:
            UpstreamDataError: If pages are missing, totals change, or the round
                changes during pagination.
            httpx.HTTPError: If a request fails.
        """
        return self._paginate_standings(
            f"{season}/constructorStandings.json", "ConstructorStandings"
        )

    def _paginate_standings(self, path: str, key: str) -> dict:
        """Read a paginated standings resource; see `driver_standings` for the result shape."""
        offset = 0
        expected_total: int | None = None
        round_number: int | None = None
        standings: list[dict] = []

        while expected_total is None or len(standings) < expected_total:
            payload = self._get(path, {"limit": self.PAGE_SIZE, "offset": offset})
            metadata = payload["MRData"]
            page_total = int(metadata["total"])
            if expected_total is None:
                expected_total = page_total
            elif page_total != expected_total:
                raise UpstreamDataError("Jolpica standings total changed during pagination")
            if expected_total == 0:
                return {"round": None, "standings": []}

            lists = metadata["StandingsTable"]["StandingsLists"]
            page_rows = lists[0][key] if lists else []
            if not page_rows:
                raise UpstreamDataError(
                    f"Jolpica returned an empty standings page at offset {offset} before {expected_total} rows"
                )
            page_round = int(lists[0]["round"])
            if round_number is None:
                round_number = page_round
            elif page_round != round_number:
                raise UpstreamDataError("Jolpica standings round changed during pagination")
            standings.extend(deepcopy(page_rows))
            if len(standings) > expected_total:
                raise UpstreamDataError(
                    f"Jolpica returned {len(standings)} standings although its total is {expected_total}"
                )
            offset += len(page_rows)

        return {"round": round_number, "standings": standings}

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
            if expected_total == 0:
                return []

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
        """Wait for the limiter, then send one GET request identifying this application (ADR-002).

        Returns the JSON body; raises `httpx.HTTPStatusError` for an error status.
        """
        self.limiter.try_acquire("jolpica")
        headers = {"User-Agent": "formula-insights-api/0.1 (portfolio project)"}
        with httpx.Client(timeout=30, headers=headers) as client:
            response = client.get(f"{self.base_url}/{path}", params=params)
            response.raise_for_status()
            return response.json()
