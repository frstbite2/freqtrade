"""Structured (JSON) logging with secret redaction."""

import json
import logging
import re
from datetime import UTC, datetime

from backend.core.config import secret_values


# user:password@ in connection URLs
_URL_PASSWORD = re.compile(r"(://[^:/@\s]+:)[^@\s]+@")


def redact(text: str) -> str:
    for value in secret_values():
        text = text.replace(value, "***")
    return _URL_PASSWORD.sub(r"\1***@", text)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return redact(json.dumps(entry, default=str))


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


def setup_logging(level: str = "INFO", json_format: bool = True) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(
        JsonFormatter()
        if json_format
        else RedactingFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
