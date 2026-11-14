"""Prometheus metrics and JSON logging."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram


class Metrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        r = self.registry
        self.active = Gauge(
            "nexora_active_sessions", "Open streaming sessions", ["mode"], registry=r
        )
        self.capacity = Gauge("nexora_capacity_sessions", "Configured session capacity", registry=r)
        self.draining = Gauge("nexora_draining", "1 while the instance drains", registry=r)
        self.work_queue = Gauge(
            "nexora_work_queue_depth", "Audio jobs waiting for a worker thread", registry=r
        )
        self.record_errors = Counter(
            "nexora_session_record_errors_total",
            "Sessions whose end could not be written to the database (check logs to bill)",
            registry=r,
        )
        self.limiter_errors = Counter(
            "nexora_limiter_errors_total",
            "Redis limiter calls that failed (fell back to this instance's count)",
            registry=r,
        )
        self.sessions = Counter(
            "nexora_sessions_total", "Sessions finished", ["mode", "outcome"], registry=r
        )
        self.rejections = Counter(
            "nexora_rejections_total", "Connections rejected", ["reason"], registry=r
        )
        self.audio_seconds = Counter(
            "nexora_audio_seconds_total", "Audio processed (input seconds)", ["mode"], registry=r
        )
        self.events = Counter(
            "nexora_turn_events_total", "Turn events emitted", ["type"], registry=r
        )
        self.chunk_seconds = Histogram(
            "nexora_chunk_processing_seconds",
            "Processing time per received audio message",
            buckets=(0.0005, 0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.25),
            registry=r,
        )
        self.session_snr_db = Histogram(
            "nexora_session_snr_db",
            "Estimated input SNR per ended session (speech level minus noise floor)",
            buckets=(0, 5, 10, 15, 20, 30, 40, 60),
            registry=r,
        )
        self.session_concealed_pct = Histogram(
            "nexora_session_concealed_percent",
            "Share of input audio concealed after packet loss, per ended session",
            buckets=(0, 0.1, 0.5, 1, 2, 5, 10, 20),
            registry=r,
        )
        self.session_clipped_pct = Histogram(
            "nexora_session_clipped_percent",
            "Share of clipped input samples, per ended session",
            buckets=(0, 0.01, 0.1, 0.5, 1, 5),
            registry=r,
        )
        self.session_start_seconds = Histogram(
            "nexora_session_start_seconds",
            "Time to get a ready audio session (pool hit or model load)",
            buckets=(0.001, 0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5),
            registry=r,
        )

    def observe_quality(self, q: dict[str, Any]) -> None:
        if "snr_db" in q:
            self.session_snr_db.observe(q["snr_db"])
        if "concealed_pct" in q:
            self.session_concealed_pct.observe(q["concealed_pct"])
        if "clipped_pct" in q:
            self.session_clipped_pct.observe(q["clipped_pct"])


_RESERVED = set(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {"message"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for k, v in record.__dict__.items():
            if k not in _RESERVED and not k.startswith("_"):
                out[k] = v
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, default=str)


def setup_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger("nexora")
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    root.propagate = False
