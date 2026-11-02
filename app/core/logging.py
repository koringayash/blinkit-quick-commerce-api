"""Structured logging configuration for Blinkit microservice.

Emits JSON logs (or human-friendly text logs) with timestamp, log level,
logger name, message, request_id, and any context-specific metadata.
"""
import contextvars
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from app.core.config import DB_ECHO, LOG_FORMAT, LOG_LEVEL

# Global context variable to carry the correlation ID across async tasks
request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

# Standard LogRecord attribute names to ignore when extracting extra kwargs
_RESERVED_RECORD_ATTRS = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "request_id", "taskName", "color_message",
}


def _extras(record: logging.LogRecord) -> dict[str, Any]:
    return {k: v for k, v in record.__dict__.items() if k not in _RESERVED_RECORD_ATTRS}


def _timestamp(record: logging.LogRecord) -> datetime:
    # Use the time the event happened, not the time it was formatted
    return datetime.fromtimestamp(record.created, tz=timezone.utc)


class StructuredJsonFormatter(logging.Formatter):
    """Formats LogRecords as a structured JSON object for ELK, Datadog, CloudWatch, etc."""

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "timestamp": _timestamp(record).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None) or request_id_ctx.get(),
        }

        # Include custom extra metadata (e.g. method, path, status_code, process_time_ms)
        log_data.update(_extras(record))

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # default=str: Decimal, datetime, UUID, etc. must never crash the logger
        return json.dumps(log_data, default=str)


class ConsoleTextFormatter(logging.Formatter):
    """Readable console formatter for local debugging."""

    def format(self, record: logging.LogRecord) -> str:
        req_id = getattr(record, "request_id", None) or request_id_ctx.get()
        ts = _timestamp(record).strftime("%Y-%m-%d %H:%M:%S UTC")
        extras = [f"{k}={v}" for k, v in _extras(record).items()]
        extra_str = f" | {', '.join(extras)}" if extras else ""

        line = f"[{ts}] [{record.levelname:<7}] [req:{req_id[:8]}] [{record.name}]: {record.getMessage()}{extra_str}"
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def setup_logging(level: str | None = None, fmt: str | None = None) -> None:
    """Configures the root logger with the appropriate formatter and log level."""
    log_level = getattr(logging, (level or LOG_LEVEL).upper(), logging.INFO)
    formatter_type = (fmt or LOG_FORMAT).lower()

    formatter: logging.Formatter = (
        ConsoleTextFormatter() if formatter_type == "text" else StructuredJsonFormatter()
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(log_level)
    root.handlers.clear()
    root.addHandler(handler)

    # Route uvicorn's own loggers through the root handler only (attaching a handler to
    # both "uvicorn" and "uvicorn.error" printed every line twice).
    for name in ("uvicorn", "uvicorn.error"):
        u_log = logging.getLogger(name)
        u_log.handlers.clear()
        u_log.propagate = True
        u_log.setLevel(log_level)

    # Our AccessLogMiddleware emits richer structured access logs; silence uvicorn's duplicate.
    access = logging.getLogger("uvicorn.access")
    access.handlers.clear()
    access.propagate = False
    access.disabled = True

    # SQL statement logging, emitted in the same structured format
    logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO if DB_ECHO else logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a logger instance configured for structured logging."""
    return logging.getLogger(name)
