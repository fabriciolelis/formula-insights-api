import socket
import threading
import time

import pytest
from fastapi.testclient import TestClient

from app import database
from app.main import app


@pytest.fixture
def silent_database():
    """A TCP endpoint that accepts connections but never answers, like a database host that hangs.

    Yields:
        A PostgreSQL URL pointing at the endpoint.
    """
    server = socket.create_server(("127.0.0.1", 0))
    accepted: list[socket.socket] = []
    stop = threading.Event()

    def accept() -> None:
        server.settimeout(0.1)
        while not stop.is_set():
            try:
                connection, _ = server.accept()
            except TimeoutError:
                continue
            accepted.append(connection)

    thread = threading.Thread(target=accept, daemon=True)
    thread.start()
    port = server.getsockname()[1]
    yield f"postgresql+psycopg://user:password@127.0.0.1:{port}/formula_insights"
    stop.set()
    thread.join()
    for connection in accepted:
        connection.close()
    server.close()


def test_ready_when_the_database_answers(sqlite_engine):
    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_unavailable_within_two_seconds_when_the_database_hangs(sqlite_engine, silent_database):
    with TestClient(app) as client:
        database.readiness_engine = database.make_readiness_engine(silent_database)
        started = time.monotonic()
        response = client.get("/ready")
        elapsed = time.monotonic() - started

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert elapsed < 2


def test_health_does_not_touch_the_database(sqlite_engine, silent_database):
    with TestClient(app) as client:
        database.readiness_engine = database.make_readiness_engine(silent_database)
        database.engine = database.make_readiness_engine(silent_database)

        assert client.get("/health").json() == {"status": "ok"}
