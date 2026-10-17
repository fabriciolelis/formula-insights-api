import argparse
import sys

from app.database import SessionLocal, create_schema
from app.importer import Importer, StandingsNotUpdatedError
from app.jolpica import JolpicaClient


def summary(season: int, counts: dict[str, int]) -> str:
    return (
        f"Imported season {season}: {counts['races']} new races, "
        f"{counts['results']} new results, {counts['driver_standings']} new driver standings, "
        f"{counts['constructor_standings']} new constructor standings"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a Formula 1 season from Jolpica.")
    parser.add_argument("season", type=int)
    args = parser.parse_args()
    create_schema()
    with SessionLocal() as session:
        try:
            counts = Importer(session, JolpicaClient()).import_season(args.season)
        except StandingsNotUpdatedError as error:
            print(summary(args.season, error.counts))
            print(f"Standings not updated: {error}", file=sys.stderr)
            sys.exit(1)
    print(summary(args.season, counts))


if __name__ == "__main__":
    main()
