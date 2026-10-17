import json
from copy import deepcopy

from app.jolpica import JolpicaClient
from tests.fixtures.jolpica.record import fixture_path


class FixtureJolpicaClient(JolpicaClient):
    """Serves recorded Jolpica responses instead of calling the network."""

    def __init__(self) -> None:
        super().__init__(base_url="https://example.test")

    def _get(self, path: str, params: dict[str, int]) -> dict:
        assert params["limit"] == self.PAGE_SIZE
        payload = json.loads(fixture_path(path, params["offset"]).read_text(encoding="utf-8"))
        return deepcopy(payload)
