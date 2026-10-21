from typing import ClassVar

import httpx
import pytest

from app import cli
from app.jolpica import UpstreamDataError
from tests.test_importer import FakeJolpica


def http_error(status: int, headers: dict[str, str] | None = None) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://example.test/2023/races.json")
    response = httpx.Response(status, headers=headers, request=request)
    return httpx.HTTPStatusError(f"HTTP {status}", request=request, response=response)


class ScriptedJolpica(FakeJolpica):
    """Records every client created and the seasons requested; fails on chosen seasons."""

    instances: ClassVar[list["ScriptedJolpica"]] = []
    failures: ClassVar[dict[int, Exception]] = {}

    def __init__(self) -> None:
        self.seasons: list[int] = []
        ScriptedJolpica.instances.append(self)

    def races(self, season):
        self.seasons.append(season)
        if season in self.failures:
            raise self.failures[season]
        return super().races(season)


@pytest.fixture
def jolpica(monkeypatch, sqlite_engine):
    ScriptedJolpica.instances = []
    ScriptedJolpica.failures = {}
    monkeypatch.setattr(cli, "JolpicaClient", ScriptedJolpica)
    return ScriptedJolpica


def test_single_season(jolpica, capsys):
    cli.main(["2024"])

    assert [client.seasons for client in jolpica.instances] == [[2024]]
    assert capsys.readouterr().out.startswith("Imported season 2024: 1 new races")


def test_range_shares_one_client_so_pacing_covers_the_whole_run(jolpica, capsys):
    cli.main(["2022", "2024"])

    assert [client.seasons for client in jolpica.instances] == [[2022, 2023, 2024]]
    assert capsys.readouterr().out.count("Imported season") == 3


def test_range_stops_at_the_first_failed_season(jolpica, capsys):
    jolpica.failures = {2023: http_error(429, {"Retry-After": "60"})}

    with pytest.raises(SystemExit) as exit_info:
        cli.main(["2022", "2025"])

    assert exit_info.value.code == 1
    assert jolpica.instances[0].seasons == [2022, 2023]
    output = capsys.readouterr()
    assert "Imported season 2022" in output.out
    assert output.err.splitlines() == [
        "Import of season 2023 failed: Jolpica rate limit exceeded (HTTP 429), retry after 60 s",
        "Skipped seasons 2024-2025; rerun from 2023 to continue.",
    ]


def test_failure_of_the_last_season_names_no_skipped_seasons(jolpica, capsys):
    jolpica.failures = {2024: UpstreamDataError("Jolpica race total changed during pagination")}

    with pytest.raises(SystemExit) as exit_info:
        cli.main(["2024"])

    assert exit_info.value.code == 1
    assert capsys.readouterr().err == (
        "Import of season 2024 failed: inconsistent data from Jolpica: "
        "Jolpica race total changed during pagination\n"
    )


def test_range_must_be_ascending(capsys):
    with pytest.raises(SystemExit) as exit_info:
        cli.parse_seasons(["2024", "2023"])

    assert exit_info.value.code == 2
    assert "last season must not be before the first season" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (http_error(429), "Jolpica rate limit exceeded (HTTP 429)"),
        (http_error(503), "Jolpica returned HTTP 503 for https://example.test/2023/races.json"),
        (httpx.ConnectError("connection refused"),
         "request to Jolpica failed: ConnectError: connection refused"),
    ],
)
def test_upstream_reason(error, reason):
    assert cli.upstream_reason(error) == reason
