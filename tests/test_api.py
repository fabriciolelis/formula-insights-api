from fastapi.testclient import TestClient

from app import database
from app.importer import Importer
from app.main import app
from tests.test_importer import FakeJolpica


def test_imported_data_is_served_from_api(sqlite_engine):
    with database.SessionLocal() as session:
        Importer(session, FakeJolpica()).import_season(2024)

    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        races = client.get("/seasons/2024/races").json()
        assert races[0]["name"] == "Test Grand Prix"
        assert client.get("/seasons/2024/standings/drivers").json()[0]["points"] == 25
        result = client.get("/seasons/2024/races/1/results").json()[0]
        assert result["driver"]["id"] == "test-driver"
