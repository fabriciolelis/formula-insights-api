from collections.abc import Callable
from urllib.parse import urlsplit

import httpx
import pytest

from app.jolpica import JolpicaClient, default_limiter
from tests.fixtures.jolpica.record import fixture_path


class RecordingLimiter:
    """Stands in for the pyrate-limiter Limiter: counts acquisitions, never waits."""

    def __init__(self) -> None:
        self.acquired = 0

    def try_acquire(self, name: str = "pyrate", weight: int = 1, **_: object) -> bool:
        self.acquired += weight
        return True


@pytest.fixture
def jolpica_http(monkeypatch) -> Callable:
    """Route the client's HTTP requests to a handler instead of the network."""
    real_client = httpx.Client

    def install(handler: Callable[[httpx.Request], httpx.Response]) -> None:
        transport = httpx.MockTransport(handler)
        monkeypatch.setattr(
            httpx, "Client", lambda **kwargs: real_client(transport=transport, **kwargs)
        )

    return install


def recorded_response(request: httpx.Request) -> httpx.Response:
    path = urlsplit(str(request.url)).path.removeprefix("/")
    offset = int(request.url.params["offset"])
    return httpx.Response(200, content=fixture_path(path, offset).read_bytes())


def read_season(client: JolpicaClient, season: int) -> None:
    client.races(season)
    client.results(season)
    client.driver_standings(season)
    client.constructor_standings(season)


def test_default_limits_match_adr_006():
    rates = [(rate.limit, rate.interval) for rate in default_limiter().buckets()[0].rates]

    assert rates == [(1, 1_000), (450, 3_600_000)]


def test_each_client_gets_its_own_default_limiter():
    assert JolpicaClient().limiter is not JolpicaClient().limiter


def test_every_request_waits_for_the_shared_limiter(jolpica_http):
    limiter = RecordingLimiter()
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        assert limiter.acquired == len(sent), "request sent before acquiring the limiter"
        return recorded_response(request)

    jolpica_http(handler)
    client = JolpicaClient(base_url="https://example.test", limiter=limiter)

    read_season(client, 2024)
    requests_per_season = len(sent)
    read_season(client, 2024)  # a second season in the same run, as in a backfill

    assert requests_per_season > 4  # results span several pages
    assert limiter.acquired == len(sent) == 2 * requests_per_season


def test_rate_limited_request_fails_immediately_without_retry(jolpica_http):
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(429, headers={"Retry-After": "60"})

    jolpica_http(handler)
    client = JolpicaClient(base_url="https://example.test", limiter=RecordingLimiter())

    with pytest.raises(httpx.HTTPStatusError) as error:
        client.races(2024)

    assert error.value.response.status_code == 429
    assert len(sent) == 1
