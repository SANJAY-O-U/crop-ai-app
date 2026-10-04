"""
Lightweight production observability: structured JSON logs + in-process event counters. No monitoring stack.

Events (the operational signals): weather_provider_success, weather_provider_failure, weather_fallback_used,
downscaling_baseline_used, invalid_weather_payload, http_request, unhandled_exception.

Never logged: request bodies, uploaded images, headers, credentials. Query strings are not logged, only the path.
"""

import json
import logging
import os
import sys
import threading
import time
import uuid
from collections import Counter
from contextvars import ContextVar

logger = logging.getLogger("cropcast")
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
_counters: Counter = Counter()
_counter_lock = threading.Lock()


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + f".{int(record.msecs):03d}Z",
                   "level": record.levelname.lower(), "event": getattr(record, "event", record.getMessage())}
        payload.update(getattr(record, "fields", {}))
        rid = request_id_var.get()
        if rid:
            payload["request_id"] = rid
        if record.exc_info:
            payload["exc_type"] = record.exc_info[0].__name__ if record.exc_info[0] else None
        return json.dumps(payload, default=str, separators=(",", ":"))


def configure_logging() -> None:
    """Idempotent. One JSON line per event on stdout (what Render collects)."""
    if any(isinstance(h.formatter, JsonFormatter) for h in logger.handlers):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    logger.propagate = False


def log_event(event: str, level: str = "info", **fields) -> None:
    logger.log(getattr(logging, level.upper(), logging.INFO), event, extra={"event": event, "fields": fields})


def count(event: str) -> None:
    with _counter_lock:
        _counters[event] += 1


def counters() -> dict:
    with _counter_lock:
        return dict(_counters)


def reset_counters() -> None:
    with _counter_lock:
        _counters.clear()


def new_request_id(incoming: str | None) -> str:
    if incoming and 0 < len(incoming) <= 64 and all(c.isalnum() or c in "-_" for c in incoming):
        return incoming
    return uuid.uuid4().hex
