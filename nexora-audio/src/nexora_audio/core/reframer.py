"""Turn arbitrary-length chunks into fixed-size frames."""

from __future__ import annotations

import numpy as np

from nexora_audio.exceptions import AudioFormatError
from nexora_audio.utils.audio_utils import Float32Array


class Reframer:
    """FIFO that accepts chunks of any length and emits frames of ``frame_size`` samples.

    Storage is preallocated and reused; it grows only if a single push exceeds capacity.
    """

    def __init__(self, channels: int, frame_size: int, initial_capacity: int | None = None) -> None:
        if channels < 1 or frame_size < 1:
            raise ValueError("channels and frame_size must be positive")
        self.channels = channels
        self.frame_size = frame_size
        capacity = max(initial_capacity or frame_size * 16, frame_size)
        self._buf: Float32Array = np.zeros((channels, capacity), dtype=np.float32)
        self._start = 0
        self._end = 0

    @property
    def available(self) -> int:
        """Buffered samples per channel."""
        return self._end - self._start

    @property
    def frames_ready(self) -> int:
        return self.available // self.frame_size

    def push(self, chunk: Float32Array) -> None:
        if chunk.ndim != 2 or chunk.shape[0] != self.channels:
            raise AudioFormatError(f"expected shape ({self.channels}, n), got {chunk.shape}")
        n = chunk.shape[1]
        if n == 0:
            return
        capacity = self._buf.shape[1]
        if self._end + n > capacity:
            live = self.available
            if live + n > capacity:
                new_cap = max(capacity * 2, live + n)
                grown = np.zeros((self.channels, new_cap), dtype=np.float32)
                grown[:, :live] = self._buf[:, self._start : self._end]
                self._buf = grown
            else:
                self._buf[:, :live] = self._buf[:, self._start : self._end]
            self._start, self._end = 0, live
        self._buf[:, self._end : self._end + n] = chunk
        self._end += n

    def pop(self, out: Float32Array | None = None) -> Float32Array | None:
        """Return the next full frame, or ``None`` if not enough data is buffered.

        If ``out`` is given it is filled in place and returned (no allocation).
        """
        if self.available < self.frame_size:
            return None
        view = self._buf[:, self._start : self._start + self.frame_size]
        if out is None:
            out = view.copy()
        else:
            out[...] = view
        self._start += self.frame_size
        if self._start == self._end:
            self._start = self._end = 0
        return out

    def drain(self) -> Float32Array:
        """Return all buffered samples (possibly fewer than a frame) and empty the buffer."""
        rest = self._buf[:, self._start : self._end].copy()
        self._start = self._end = 0
        return rest

    def reset(self) -> None:
        self._start = self._end = 0
