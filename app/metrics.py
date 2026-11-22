"""HTTP request metrics for the SLOs, exposed for Prometheus (ADR-009).

OpenTelemetry instruments every request and its Prometheus exporter serves the
result on GET /metrics: `http_server_request_duration_seconds`, a histogram
labelled by route template, method, and status code. Its default buckets
include 0.5 s, the latency SLO's threshold; its `_count` is the request
counter. Health, readiness, and the metrics endpoint itself are not measured.

/metrics is served on the API's own port. Before the API is exposed through an
Ingress or any public endpoint, block /metrics there or move it to a separate
port: the metrics are meant for Prometheus only.
"""

import os

# The stable HTTP semantic conventions (seconds, `http.route`); without this
# opt-in the instrumentation still emits the old ones (milliseconds, raw
# targets). Set before the instrumentation reads it.
os.environ.setdefault("OTEL_SEMCONV_STABILITY_OPT_IN", "http")

from fastapi import FastAPI, Response
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

EXCLUDED_URLS = "/health$,/ready$,/metrics$"


def instrument(app: FastAPI) -> None:
    """Measure the app's requests and serve the metrics on GET /metrics.

    Args:
        app: The FastAPI application to instrument.
    """
    provider = MeterProvider(
        resource=Resource.create({"service.name": "formula-insights-api"}),
        metric_readers=[PrometheusMetricReader()],
    )
    FastAPIInstrumentor.instrument_app(
        app, meter_provider=provider, excluded_urls=EXCLUDED_URLS
    )

    @app.get("/metrics", include_in_schema=False)
    def metrics() -> Response:
        """Prometheus text exposition of the request metrics."""
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
