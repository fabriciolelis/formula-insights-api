import argparse

from app.database import SessionLocal, create_schema
from app.importer import Importer
from app.jolpica import JolpicaClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a Formula 1 season from Jolpica.")
    parser.add_argument("season", type=int)
    args = parser.parse_args()
    create_schema()
    with SessionLocal() as session:
        counts = Importer(session, JolpicaClient()).import_season(args.season)
    print(
        f"Imported season {args.season}: {counts['races']} new races, "
        f"{counts['results']} new results, {counts['driver_standings']} new driver standings, "
        f"{counts['constructor_standings']} new constructor standings"
    )


if __name__ == "__main__":
    main()
