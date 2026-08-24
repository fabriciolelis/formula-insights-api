import os

import httpx


class JolpicaClient:
    """Small client for the Jolpica Ergast-compatible historical API."""

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or os.getenv("JOLPICA_BASE_URL", "https://api.jolpi.ca/ergast/f1")

    def races(self, season: int) -> list[dict]:
        return self._get(f"{season}/races.json", {"limit": 100})["MRData"]["RaceTable"]["Races"]

    def results(self, season: int) -> list[dict]:
        return self._get(f"{season}/results.json", {"limit": 2000})["MRData"]["RaceTable"]["Races"]

    def _get(self, path: str, params: dict[str, int]) -> dict:
        headers = {"User-Agent": "formula-insights-api/0.1 (portfolio project)"}
        with httpx.Client(timeout=30, headers=headers) as client:
            response = client.get(f"{self.base_url}/{path}", params=params)
            response.raise_for_status()
            return response.json()
