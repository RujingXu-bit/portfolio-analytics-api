import json
import logging
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from typing import Final

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_STRUCTURED_FIELDS: Final = (
    "event",
    "request_id",
    "http_method",
    "http_route",
    "status_code",
    "duration_ms",
    "outcome",
    "cache_name",
    "cache_status",
    "provider",
    "symbol",
    "error_category",
    "error_type",
)


def bind_request_id(request_id: str) -> Token[str | None]:
    return _request_id.set(request_id)


def reset_request_id(token: Token[str | None]) -> None:
    _request_id.reset(token)


def current_request_id() -> str | None:
    return _request_id.get()


class JsonLogFormatter(logging.Formatter):
    """Serialize a deliberately small, secret-safe log record schema."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field_name in _STRUCTURED_FIELDS:
            value = getattr(record, field_name, None)
            if value is not None:
                payload[field_name] = value
        if "request_id" not in payload:
            request_id = current_request_id()
            if request_id is not None:
                payload["request_id"] = request_id
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def configure_logging(level: str = "INFO") -> None:
    """Configure application and Uvicorn logs through one JSON handler."""

    numeric_level = logging.getLevelNamesMapping().get(level.upper())
    if numeric_level is None:
        raise ValueError(f"unsupported log level {level!r}")

    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(numeric_level)

    for logger_name in ("uvicorn", "uvicorn.error"):
        configured_logger = logging.getLogger(logger_name)
        configured_logger.handlers.clear()
        configured_logger.propagate = True
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers.clear()
    access_logger.propagate = False
    access_logger.disabled = True

    for logger_name in ("httpcore", "httpx", "openai"):
        logging.getLogger(logger_name).setLevel(logging.WARNING)
