"""Lightweight timing statistics."""

from __future__ import annotations

from collections import deque

import numpy as np


class TimingStats:
    """Rolling window of processing durations (seconds) with percentile summaries."""

    def __init__(self, maxlen: int = 10_000) -> None:
        self._d: deque[float] = deque(maxlen=maxlen)
        self.total_s = 0.0
        self.count = 0

    def add(self, seconds: float) -> None:
        self._d.append(seconds)
        self.total_s += seconds
        self.count += 1

    def percentile_ms(self, q: float) -> float:
        if not self._d:
            return 0.0
        return float(np.percentile(np.fromiter(self._d, dtype=np.float64), q)) * 1000.0

    @property
    def p50_ms(self) -> float:
        return self.percentile_ms(50)

    @property
    def p99_ms(self) -> float:
        return self.percentile_ms(99)

    @property
    def max_ms(self) -> float:
        return max(self._d, default=0.0) * 1000.0

    def reset(self) -> None:
        self._d.clear()
        self.total_s = 0.0
        self.count = 0
