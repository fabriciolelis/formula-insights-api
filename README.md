# Formula Insights API

API and scheduled ingestion service for historical Formula 1 data.

## Purpose

This service imports public Formula 1 data into PostgreSQL and provides a small, reliable HTTP API for races, results, and championship standings. It is the first workload running on the Formula Insights Platform.

The project is intentionally small. Its primary purpose is to validate platform delivery, operational, and observability capabilities rather than to become a feature-complete sports application.

## Release 1 endpoints

\`\`\`text
GET /health
GET /seasons/{year}/races
GET /seasons/{year}/standings/drivers
GET /seasons/{year}/standings/constructors
GET /seasons/{year}/races/{round}/results
\`\`\`

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

Those responsibilities belong to \`platform-infrastructure\` and \`platform-gitops\`.

## Local development

> Commands and language runtime will be added when implementation starts in Sprint 1.

The local setup must eventually start PostgreSQL, run one idempotent import, start the API, and execute tests without depending on AWS.

## Quality gates

Every pull request must, at minimum:

- run unit tests;
- run an end-to-end import test against a disposable database;
- build the container image;
- check formatting and static analysis;
- scan dependencies and container image vulnerabilities.

## Delivery

GitHub Actions builds and tests the image. It does not deploy directly to Kubernetes. A reviewed image-version update in \`platform-gitops\` is reconciled into the cluster by Argo CD.

## Documentation

Platform decisions, SLOs, runbooks, and postmortems live in the \`formula-docs\` repository. See in particular ADR-002 (data source) and ADR-003 (GitOps delivery).

## Security

- Never commit credentials or local \`.env\` files.
- Read credentials only from environment variables or the runtime secret mechanism.
- Use least-privilege database credentials.
- Treat all upstream data as untrusted input.
