"""Request metrics, read the way Prometheus reads them: from GET /metrics."""

from fastapi.testclient import TestClient
from prometheus_client.parser import text_string_to_metric_families

from app import database
from app.importer import Importer
from app.main import app
from tests.test_importer import FakeJolpica

DURATION = "http_server_request_duration_seconds"


def scrape(client: TestClient) -> list:
    """Samples of the request-duration histogram, as exposed on /metrics."""
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    return [
        sample
        for family in text_string_to_metric_families(response.text)
        if family.name == DURATION
        for sample in family.samples
    ]


def value(samples: list, suffix: str, **labels: str) -> float:
    """Sum of the samples named DURATION + suffix whose labels include `labels`."""
    return sum(
        sample.value
        for sample in samples
        if sample.name == DURATION + suffix and labels.items() <= sample.labels.items()
    )


def test_requests_are_counted_per_route_template_and_status(sqlite_engine):
    with database.SessionLocal() as session:
        Importer(session, FakeJolpica()).import_season(2024)
    route = {"http_route": "/seasons/{year}/races/{round_number}/results"}

    with TestClient(app) as client:
        before = scrape(client)
        client.get("/seasons/2024/races/1/results")
        client.get("/seasons/2024/races/1/results")
        client.get("/seasons/2024/races/99/results")
        after = scrape(client)

    ok = {**route, "http_request_method": "GET", "http_response_status_code": "200"}
    missing = {**route, "http_request_method": "GET", "http_response_status_code": "404"}
    assert value(after, "_count", **ok) - value(before, "_count", **ok) == 2
    assert value(after, "_count", **missing) - value(before, "_count", **missing) == 1


def test_duration_histogram_has_a_bucket_at_the_latency_slo_threshold(sqlite_engine):
    with TestClient(app) as client:
        client.get("/seasons/2024/races")
        samples = scrape(client)

    buckets = {
        sample.labels["le"]
        for sample in samples
        if sample.name == DURATION + "_bucket" and sample.labels["http_route"] == "/seasons/{year}/races"
    }
    assert "0.5" in buckets


def test_labels_hold_route_templates_never_raw_paths(sqlite_engine):
    with TestClient(app) as client:
        client.get("/seasons/1987/races")
        client.get("/seasons/1987/standings/drivers")
        text = client.get("/metrics").text

    assert "1987" not in text
    assert 'http_route="/seasons/{year}/standings/drivers"' in text


def test_health_readiness_and_metrics_are_not_measured(sqlite_engine):
    with TestClient(app) as client:
        client.get("/health")
        client.get("/ready")
        client.get("/metrics")
        routes = {sample.labels.get("http_route") for sample in scrape(client)}

    assert routes.isdisjoint({"/health", "/ready", "/metrics"})
