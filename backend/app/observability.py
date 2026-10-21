"""Structured JSON logging, correlation IDs and lightweight in-process metrics."""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from collections import defaultdict
from contextvars import ContextVar
from datetime import UTC, datetime

correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="-")

_RESERVED = set(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {"message", "asctime"}
_SECRET_HINTS = ("api_key", "authorization", "password", "secret", "token")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "correlation_id": correlation_id_var.get(),
        }
        for key, value in record.__dict__.items():
            if key in _RESERVED or key.startswith("_"):
                continue
            payload[key] = "[redacted]" if any(h in key.lower() for h in _SECRET_HINTS) else value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    for noisy in ("httpx", "httpcore", "anthropic"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def new_correlation_id() -> str:
    return uuid.uuid4().hex


class Metrics:
    """Thread-safe counters and latency summaries exposed at /api/v1/metrics.

    Deliberately tiny: swap for an OpenTelemetry/Prometheus exporter when deployed.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.counters: dict[str, int] = defaultdict(int)
        self.latency: dict[str, list[float]] = defaultdict(list)

    def incr(self, name: str, value: int = 1) -> None:
        with self._lock:
            self.counters[name] += value

    def observe(self, name: str, ms: float) -> None:
        with self._lock:
            bucket = self.latency[name]
            bucket.append(ms)
            if len(bucket) > 500:
                del bucket[:250]

    def snapshot(self) -> dict:
        with self._lock:
            lat = {}
            for name, values in self.latency.items():
                s = sorted(values)
                lat[name] = {
                    "count": len(s),
                    "p50_ms": round(s[len(s) // 2], 1),
                    "p95_ms": round(s[min(len(s) - 1, int(len(s) * 0.95))], 1),
                }
            return {"counters": dict(self.counters), "latency": lat}


metrics = Metrics()


class Timer:
    def __enter__(self) -> Timer:
        self.start = time.perf_counter()
        return self

    def __exit__(self, *exc) -> None:
        self.ms = (time.perf_counter() - self.start) * 1000
