from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app import database
from app.importer import Importer
from app.main import app
from app.models import Base
from tests.test_importer import FakeJolpica


def test_imported_data_is_served_from_api(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    database.engine = engine
    database.SessionLocal.configure(bind=engine)
    Base.metadata.create_all(engine)
    with database.SessionLocal() as session:
        Importer(session, FakeJolpica()).import_season(2024)

    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        races = client.get("/seasons/2024/races").json()
        assert races[0]["name"] == "Test Grand Prix"
        assert client.get("/seasons/2024/standings/drivers").json()[0]["points"] == 25
        result = client.get("/seasons/2024/races/1/results").json()[0]
        assert result["driver"]["id"] == "test-driver"
