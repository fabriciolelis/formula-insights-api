from copy import deepcopy

import pytest

from app.jolpica import JolpicaClient, UpstreamDataError


def result(driver_id: str) -> dict:
    return {
        "position": "1",
        "positionText": "1",
        "points": "25",
        "status": "Finished",
        "Driver": {
            "driverId": driver_id,
            "givenName": "Test",
            "familyName": "Driver",
            "nationality": "Test",
        },
        "Constructor": {
            "constructorId": "test-team",
            "name": "Test Team",
            "nationality": "Test",
        },
    }


def page(total: int, races: list[dict]) -> dict:
    return {"MRData": {"total": str(total), "RaceTable": {"Races": races}}}


class StubJolpicaClient(JolpicaClient):
    def __init__(self, pages: dict[int, dict]) -> None:
        super().__init__(base_url="https://example.test")
        self.pages = pages
        self.requests: list[dict[str, int]] = []

    def _get(self, path: str, params: dict[str, int]) -> dict:
        assert path == "2024/results.json"
        self.requests.append(params)
        return deepcopy(self.pages[params["offset"]])


def test_results_paginates_and_merges_partial_races():
    client = StubJolpicaClient(
        {
            0: page(
                3,
                [
                    {
                        "round": "1",
                        "raceName": "First",
                        "Results": [result("driver-1"), result("driver-2")],
                    }
                ],
            ),
            2: page(
                3,
                [
                    {
                        "round": "2",
                        "raceName": "Second",
                        "Results": [result("driver-3")],
                    }
                ],
            ),
        }
    )

    races = client.results(2024)

    assert client.requests == [{"limit": 100, "offset": 0}, {"limit": 100, "offset": 2}]
    assert [race["round"] for race in races] == ["1", "2"]
    assert [entry["Driver"]["driverId"] for entry in races[0]["Results"]] == [
        "driver-1",
        "driver-2",
    ]
    assert [entry["Driver"]["driverId"] for entry in races[1]["Results"]] == ["driver-3"]


def test_results_rejects_an_incomplete_page_sequence():
    client = StubJolpicaClient(
        {
            0: page(
                3,
                [
                    {
                        "round": "1",
                        "raceName": "First",
                        "Results": [result("driver-1"), result("driver-2")],
                    }
                ],
            ),
            2: page(3, []),
        }
    )

    with pytest.raises(UpstreamDataError, match="empty result page"):
        client.results(2024)


def standings_page(total: int, round_number: str, rows: list[dict]) -> dict:
    return {
        "MRData": {
            "total": str(total),
            "StandingsTable": {
                "StandingsLists": [{"round": round_number, "DriverStandings": rows}]
            },
        }
    }


class StubStandingsClient(JolpicaClient):
    def __init__(self, pages: dict[int, dict]) -> None:
        super().__init__(base_url="https://example.test")
        self.pages = pages

    def _get(self, path: str, params: dict[str, int]) -> dict:
        assert path == "2024/driverStandings.json"
        return deepcopy(self.pages[params["offset"]])


def test_driver_standings_paginate_and_keep_the_round():
    client = StubStandingsClient(
        {
            0: standings_page(3, "24", [{"position": "1"}, {"position": "2"}]),
            2: standings_page(3, "24", [{"position": "3"}]),
        }
    )

    table = client.driver_standings(2024)

    assert table["round"] == 24
    assert [row["position"] for row in table["standings"]] == ["1", "2", "3"]


def test_driver_standings_reject_a_round_change_during_pagination():
    client = StubStandingsClient(
        {
            0: standings_page(3, "23", [{"position": "1"}, {"position": "2"}]),
            2: standings_page(3, "24", [{"position": "3"}]),
        }
    )

    with pytest.raises(UpstreamDataError, match="round changed"):
        client.driver_standings(2024)
