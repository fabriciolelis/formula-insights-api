"""Command-line entry point for importing seasons: `python -m app.cli <first> [<last>]` or `current`."""

import argparse
import logging
import sys
from datetime import UTC, date, datetime

import httpx

from app.database import SchemaNotReadyError, SessionLocal, ensure_schema_ready
from app.importer import Importer, StandingsNotUpdatedError
from app.jolpica import JolpicaClient, UpstreamDataError
from app.logs import configure_logging

logger = logging.getLogger(__name__)

ENTITIES = ("races", "results", "driver_standings", "constructor_standings")


def summary(season: int, counts: dict[str, int]) -> str:
    """Format the per-entity counts of an import as one line.

    Args:
        season: The imported season.
        counts: New rows per entity, as returned by `Importer.import_season`.

    Returns:
        A human-readable summary line.
    """
    return (
        f"Imported season {season}: {counts['races']} new races, "
        f"{counts['results']} new results, {counts['driver_standings']} new driver standings, "
        f"{counts['constructor_standings']} new constructor standings"
    )


def upstream_reason(error: httpx.HTTPError | UpstreamDataError) -> str:
    """Describe a failure caused by Jolpica in one line.

    Args:
        error: The HTTP or data error raised while reading from Jolpica.

    Returns:
        A short reason; for `429`, it includes `Retry-After` when Jolpica sends it.
    """
    if isinstance(error, UpstreamDataError):
        return f"inconsistent data from Jolpica: {error}"
    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
        if status == 429:
            retry_after = error.response.headers.get("Retry-After")
            suffix = f", retry after {retry_after} s" if retry_after else ""
            return f"Jolpica rate limit exceeded (HTTP 429){suffix}"
        return f"Jolpica returned HTTP {status} for {error.request.url}"
    return f"request to Jolpica failed: {type(error).__name__}: {error}"


CURRENT = "current"


def season_argument(value: str) -> int | str:
    """Accept a season year or the word `current`.

    Args:
        value: The command-line value.

    Returns:
        The year as an integer, or `CURRENT`.

    Raises:
        argparse.ArgumentTypeError: If the value is neither.
    """
    if value == CURRENT:
        return CURRENT
    try:
        return int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"expected a season year or '{CURRENT}', got '{value}'"
        ) from None


def parse_seasons(argv: list[str] | None = None, today: date | None = None) -> range:
    """Read the season or inclusive season range from the command line.

    `current` stands for the season of the current calendar year in UTC, so a
    scheduled daily import needs no yearly change.

    Args:
        argv: Arguments without the program name; defaults to `sys.argv[1:]`.
        today: The date that `current` resolves against; defaults to today in UTC.

    Returns:
        The seasons to import, in ascending order.
    """
    parser = argparse.ArgumentParser(
        description="Import Formula 1 seasons from Jolpica, paced as ADR-006 requires."
    )
    parser.add_argument(
        "first",
        type=season_argument,
        help=f"season to import, first season of a range, or '{CURRENT}' for this UTC year",
    )
    parser.add_argument("last", type=int, nargs="?", help="last season of the range (inclusive)")
    args = parser.parse_args(argv)
    if args.first == CURRENT:
        if args.last is not None:
            parser.error(f"'{CURRENT}' imports one season and takes no last season")
        season = (today or datetime.now(UTC).date()).year
        return range(season, season + 1)
    last = args.first if args.last is None else args.last
    if last < args.first:
        parser.error("last season must not be before the first season")
    return range(args.first, last + 1)


def main(argv: list[str] | None = None) -> None:
    """Import the season or season range given on the command line.

    All seasons share one Jolpica client, so pacing covers the whole run. The
    import stops at the first season that fails and exits with code 1 and the
    reason, so a scheduled run is reported as failed (ADR-006). Seasons
    imported before the failure are kept; imports are idempotent, so a rerun
    can start from the failed season. Nothing is imported unless the database
    schema is migrated (ADR-007).

    Args:
        argv: Arguments without the program name; defaults to `sys.argv[1:]`.
    """
    configure_logging()
    seasons = parse_seasons(argv)
    run = ImportRun(seasons)
    try:
        ensure_schema_ready()
    except SchemaNotReadyError as error:
        print(f"Import not started: {error}", file=sys.stderr)
        run.log_summary("failure", reason=str(error))
        sys.exit(1)
    client = JolpicaClient()
    for season in seasons:
        with SessionLocal() as session:
            try:
                counts = Importer(session, client).import_season(season)
            except StandingsNotUpdatedError as error:
                run.log_season(season, error.counts)
                fail(run, season, f"standings not updated: {error}")
            except (httpx.HTTPError, UpstreamDataError) as error:
                fail(run, season, upstream_reason(error))
        run.log_season(season, counts)
        run.seasons_imported += 1
    run.log_summary("success")


class ImportRun:
    """Tracks one import for its log lines and the summary line that ends it.

    The summary line, with the condition of the import's Job, is the ingestion
    signal (platform-docs#10): every import ends with exactly one.
    """

    def __init__(self, seasons: range) -> None:
        self.seasons = seasons
        self.seasons_imported = 0
        self.counts = dict.fromkeys(ENTITIES, 0)

    def log_season(self, season: int, counts: dict[str, int]) -> None:
        """Log the rows one season added and add them to the run's totals.

        Args:
            season: The season.
            counts: New rows per entity.
        """
        for entity in ENTITIES:
            self.counts[entity] += counts[entity]
        logger.info(summary(season, counts), extra={"season": season, "counts": counts})

    def log_summary(self, outcome: str, **fields: object) -> None:
        """Log the summary line that ends the import.

        Args:
            outcome: `success` or `failure`.
            **fields: Extra fields, such as `reason` and `failed_season`.
        """
        logger.info(
            "Import summary",
            extra={
                "outcome": outcome,
                "first_season": self.seasons[0],
                "last_season": self.seasons[-1],
                "seasons_imported": self.seasons_imported,
                "counts": self.counts,
                **fields,
            },
        )


def fail(run: ImportRun, season: int, reason: str) -> None:
    """Report a failed season on stderr, log the summary line, and exit with code 1.

    Args:
        run: The import, which knows all its seasons, to say where a rerun should start.
        season: The season that failed.
        reason: Why the season failed.
    """
    seasons = run.seasons
    run.log_summary("failure", failed_season=season, reason=reason)
    print(f"Import of season {season} failed: {reason}", file=sys.stderr)
    remaining = range(season + 1, seasons[-1] + 1)
    if remaining:
        skipped = (
            f"season {remaining[0]}"
            if len(remaining) == 1
            else f"seasons {remaining[0]}-{remaining[-1]}"
        )
        print(f"Skipped {skipped}; rerun from {season} to continue.", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
