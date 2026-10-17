"""Record Jolpica responses used by the offline test fixtures.

Run from the repository root: uv run python -m tests.fixtures.jolpica.record 2024
"""

import json
import sys
from pathlib import Path

from app.jolpica import JolpicaClient

FIXTURE_ROOT = Path(__file__).parent


def fixture_path(path: str, offset: int) -> Path:
    return FIXTURE_ROOT / path.removesuffix(".json") / f"offset-{offset:04d}.json"


class RecordingJolpicaClient(JolpicaClient):
    def _get(self, path: str, params: dict[str, int]) -> dict:
        payload = super()._get(path, params)
        target = fixture_path(path, params["offset"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        return payload


def main() -> None:
    season = int(sys.argv[1])
    client = RecordingJolpicaClient()
    client.races(season)
    client.results(season)


if __name__ == "__main__":
    main()
