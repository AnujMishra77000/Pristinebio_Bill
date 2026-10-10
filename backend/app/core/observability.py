"""Small, dependency-free operational telemetry primitives.

Request bodies, query strings, cookies and authorization headers are never
logged. The JSON events are suitable for a collector or error-tracking agent
without making finance data part of an application cache.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from contextvars import ContextVar
from typing import Awaitable, Callable

from starlette.requests import Request
from starlette.responses import Response


request_id_context: ContextVar[str] = ContextVar("request_id", default="-")
logger = logging.getLogger("billing.request")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        event = getattr(record, "event", "application_log")
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "event": event,
            "request_id": request_id_context.get(),
            "message": record.getMessage(),
        }
        for field in ("method", "path", "status_code", "duration_ms", "exception_type"):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=True)


def configure_logging() -> None:
    root = logging.getLogger()
    if not any(isinstance(handler.formatter, JsonFormatter) for handler in root.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        root.handlers.clear()
        root.addHandler(handler)
        root.setLevel(logging.INFO)


def new_request_id(value: str | None) -> str:
    if value and len(value) <= 128 and all(char.isalnum() or char in "._-" for char in value):
        return value
    return str(uuid.uuid4())


async def request_logging_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    request_id = new_request_id(request.headers.get("X-Request-ID"))
    token = request_id_context.set(request_id)
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "Unhandled request exception",
            extra={"event": "unhandled_exception", "method": request.method, "path": request.url.path, "exception_type": "internal"},
        )
        raise
    finally:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        status_code = locals().get("response").status_code if "response" in locals() else 500
        logger.info(
            "Request completed",
            extra={"event": "request_completed", "method": request.method, "path": request.url.path, "status_code": status_code, "duration_ms": duration_ms},
        )
        request_id_context.reset(token)
    response.headers["X-Request-ID"] = request_id
    return response


def capture_exception(exc: Exception) -> None:
    """Emit a redacted error event for the configured log/error collector."""
    logger.error(
        "Unhandled application error captured",
        extra={"event": "error_tracking", "exception_type": type(exc).__name__},
        exc_info=exc,
    )
