"""JSON logging: one JSON object per line, so a cluster's log tooling can filter by field."""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import TextIO

# Attributes every LogRecord has; anything else on a record came from `extra=`.
_STANDARD_ATTRIBUTES = set(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {
    "message",
    "asctime",
    "taskName",
}

# Uvicorn installs its own handlers on these and stops propagation.
_UVICORN_LOGGERS = ("uvicorn", "uvicorn.access", "uvicorn.error")


class JsonFormatter(logging.Formatter):
    """Format a record as one JSON object: timestamp, level, logger, message, and extra fields."""

    def format(self, record: logging.LogRecord) -> str:
        """Render the record as a single JSON line.

        Args:
            record: The log record.

        Returns:
            The JSON text, without a trailing newline.
        """
        entry = {
            "timestamp": datetime.fromtimestamp(record.created, UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        entry.update(
            (key, value)
            for key, value in vars(record).items()
            if key not in _STANDARD_ATTRIBUTES and not key.startswith("_")
        )
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def configure_logging(stream: TextIO | None = None, level: int = logging.INFO) -> None:
    """Send every log record, including uvicorn's, to `stream` as JSON lines.

    Args:
        stream: Where to write; defaults to standard output.
        level: The minimum level to log.
    """
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    for name in _UVICORN_LOGGERS:
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
