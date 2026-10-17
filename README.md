# Formula Insights API

API and scheduled ingestion service for historical Formula 1 data.

## Purpose

This service imports public Formula 1 data into PostgreSQL and provides a small, reliable HTTP API for races, results, and championship standings. It is the first workload running on the Formula Insights Platform.

The project is intentionally small. Its primary purpose is to validate platform delivery, operational, and observability capabilities rather than to become a feature-complete sports application.

## Release 1 endpoints

```text
GET /health
GET /seasons/{year}/races
GET /seasons/{year}/standings/drivers
GET /seasons/{year}/standings/constructors
GET /seasons/{year}/races/{round}/results
```

Standings mirror the official championship tables published by Jolpica after
the latest imported round, so they include sprint points, penalties, and
exclusions. Excluded entries have no numeric `position` (for example,
`position_text` is `E`) and are listed last.

Races and results are saved first. Standings replace the stored ones only when
they are complete and from the same round as the latest results; otherwise the
previous standings are kept and the import exits with code 1 and the reason,
so a scheduled run shows as failed and retries next time. Seasons imported
before standings were added return empty standings until they are imported
again.

## Responsibilities

- Validate and serve HTTP requests.
- Import data from the configured Formula 1 data source.
- Persist normalized data in PostgreSQL.
- Emit structured logs and Prometheus metrics.
- Provide health and readiness endpoints for Kubernetes.

## Non-responsibilities

- Provisioning cloud infrastructure.
- Applying resources to a Kubernetes cluster.
- Storing deployment configuration or secrets.

Those responsibilities belong to `platform-infrastructure` and `platform-gitops`.

## Local development

The Sprint 1 vertical slice runs without AWS or Kubernetes. It starts a local
PostgreSQL database, imports one historical season from Jolpica, and serves the
documented read endpoints.

```powershell
docker compose up -d postgres
Copy-Item .env.example .env
uv sync --extra dev
uv run python -m app.cli 2024
uv run uvicorn app.main:app --reload
```

The API is then available at `http://localhost:8000`; interactive endpoint
documentation is at `/docs`. Re-running `uv run python -m app.cli 2024` is safe: the
importer updates existing rows rather than creating duplicates.

Dependencies are locked in `uv.lock`; install [uv](https://docs.astral.sh/uv/) first.
After changing dependencies in `pyproject.toml`, run `uv lock` and commit the
updated lockfile.

Run the first automated check with:

```powershell
uv run pytest
uv run ruff check .
```

Tests use recorded Jolpica responses in `tests/fixtures/jolpica`, so they run
offline. The PostgreSQL end-to-end test runs only when `TEST_DATABASE_URL` is
set (in CI it always runs, and fails if the URL is missing). It works in a
throwaway schema that it drops afterwards. Use a separate test database so an
interrupted run never leaves anything in your development data:

```powershell
docker compose exec postgres createdb -U formula_insights formula_insights_test
$env:TEST_DATABASE_URL = "postgresql+psycopg://formula_insights:formula_insights@localhost:5432/formula_insights_test"
uv run pytest
```

To re-record the fixtures, run `uv run python -m tests.fixtures.jolpica.record 2024`.

Static analysis uses [Semgrep](https://semgrep.dev/) with the `p/python` and
`p/secrets` rulesets; CI fails on ERROR-severity findings. To run it locally,
install it with `uv tool install semgrep`, then:

```powershell
semgrep scan --config p/python --config p/secrets --metrics off
```

The committed `.mcp.json` registers Semgrep's MCP server (`semgrep mcp`) for
AI coding assistants such as Claude Code; it requires the `semgrep` command on
your `PATH`.

## Quality gates

Every pull request must, at minimum:

- run unit tests;
- run an end-to-end import test against a disposable PostgreSQL database;
- build the container image;
- check formatting and static analysis;
- scan dependencies and container image vulnerabilities.

## Delivery

GitHub Actions builds and tests the image. It does not deploy directly to Kubernetes. A reviewed image-version update in `platform-gitops` is reconciled into the cluster by Argo CD.

## Documentation

Platform decisions, SLOs, runbooks, and postmortems live in the `platform-docs` repository. See in particular ADR-002 (data source) and ADR-003 (GitOps delivery).

## Security

- Never commit credentials or local `.env` files.
- Read credentials only from environment variables or the runtime secret mechanism.
- Use least-privilege database credentials.
- Treat all upstream data as untrusted input.
