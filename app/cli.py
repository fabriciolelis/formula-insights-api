"""Command-line entry point for importing seasons: `python -m app.cli <first> [<last>]`."""

import argparse
import sys

import httpx

from app.database import SessionLocal, create_schema
from app.importer import Importer, StandingsNotUpdatedError
from app.jolpica import JolpicaClient, UpstreamDataError


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


def parse_seasons(argv: list[str] | None = None) -> range:
    """Read the season or inclusive season range from the command line.

    Args:
        argv: Arguments without the program name; defaults to `sys.argv[1:]`.

    Returns:
        The seasons to import, in ascending order.
    """
    parser = argparse.ArgumentParser(
        description="Import Formula 1 seasons from Jolpica, paced as ADR-006 requires."
    )
    parser.add_argument("first", type=int, help="season to import, or first season of a range")
    parser.add_argument("last", type=int, nargs="?", help="last season of the range (inclusive)")
    args = parser.parse_args(argv)
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
    can start from the failed season.

    Args:
        argv: Arguments without the program name; defaults to `sys.argv[1:]`.
    """
    seasons = parse_seasons(argv)
    create_schema()
    client = JolpicaClient()
    for season in seasons:
        with SessionLocal() as session:
            try:
                counts = Importer(session, client).import_season(season)
            except StandingsNotUpdatedError as error:
                print(summary(season, error.counts))
                fail(season, seasons, f"standings not updated: {error}")
            except (httpx.HTTPError, UpstreamDataError) as error:
                fail(season, seasons, upstream_reason(error))
        print(summary(season, counts))


def fail(season: int, seasons: range, reason: str) -> None:
    """Report a failed season on stderr and exit with code 1.

    Args:
        season: The season that failed.
        seasons: All seasons of the run, to say where a rerun should start.
        reason: Why the season failed.
    """
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
