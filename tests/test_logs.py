import io
import json
import logging

import pytest

from app.logs import configure_logging


@pytest.fixture
def log_output():
    """Configure JSON logging into a buffer, then restore the root logger."""
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    stream = io.StringIO()
    configure_logging(stream)
    yield stream
    root.handlers[:] = handlers
    root.setLevel(level)


def lines(stream: io.StringIO) -> list[dict]:
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def test_each_record_is_one_json_line_with_its_extra_fields(log_output):
    logging.getLogger("app.importer").info("Imported season", extra={"season": 2024})

    [record] = lines(log_output)
    assert record["level"] == "INFO"
    assert record["logger"] == "app.importer"
    assert record["message"] == "Imported season"
    assert record["season"] == 2024
    assert record["timestamp"].endswith("Z")


def test_message_arguments_are_formatted(log_output):
    logging.getLogger("app.database").warning("Readiness check timed out after %s s", 1.5)

    assert lines(log_output)[0]["message"] == "Readiness check timed out after 1.5 s"


def test_an_exception_stays_inside_the_json_line(log_output):
    try:
        raise ValueError("bad row")
    except ValueError:
        logging.getLogger("app").exception("Import failed")

    [record] = lines(log_output)
    assert "ValueError: bad row" in record["exception"]


def test_uvicorn_loggers_write_through_the_same_json_handler(log_output):
    logging.getLogger("uvicorn.access").info('127.0.0.1 - "GET /ready HTTP/1.1" 200')
    logging.getLogger("uvicorn.error").info("Application startup complete.")

    assert [record["logger"] for record in lines(log_output)] == [
        "uvicorn.access",
        "uvicorn.error",
    ]
