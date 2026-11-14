"""Single-producer single-consumer ring buffer for float32 audio.

The audio callback (PortAudio's thread) writes and the processing thread reads, or the other
way round. Each side only moves its own index, so no lock is needed (Python's GIL makes the
index stores atomic). Overflows (writer faster than reader) drop the newest samples and are
counted; underruns (reader faster) are counted by the caller.
"""

from __future__ import annotations

import numpy as np

from nexora_audio.utils.audio_utils import Float32Array


class RingBuffer:
    def __init__(self, capacity: int) -> None:
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        self._buf = np.zeros(capacity + 1, np.float32)  # one slot kept free: full != empty
        self._size = capacity + 1
        self._r = 0  # moved by the reader only
        self._w = 0  # moved by the writer only
        self.dropped = 0  # samples lost to overflow

    @property
    def capacity(self) -> int:
        return self._size - 1

    def available(self) -> int:
        """Samples ready to read."""
        return (self._w - self._r) % self._size

    def free(self) -> int:
        return self.capacity - self.available()

    def write(self, x: Float32Array) -> int:
        """Append samples; returns how many fit (the rest are dropped and counted)."""
        x = np.asarray(x, np.float32).reshape(-1)
        n = min(len(x), self.free())
        self.dropped += len(x) - n
        w = self._w
        first = min(n, self._size - w)
        self._buf[w : w + first] = x[:first]
        self._buf[: n - first] = x[first:n]
        self._w = (w + n) % self._size  # publish after the data is in place
        return n

    def read(self, n: int) -> Float32Array | None:
        """Take exactly ``n`` samples, or None (nothing taken) if fewer are ready."""
        if self.available() < n:
            return None
        r = self._r
        first = min(n, self._size - r)
        out = np.concatenate([self._buf[r : r + first], self._buf[: n - first]])
        self._r = (r + n) % self._size
        return out
