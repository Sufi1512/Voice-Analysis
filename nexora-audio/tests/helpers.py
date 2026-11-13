"""Test-only processors with exactly known behaviour (not shipped in the package)."""

from __future__ import annotations

from typing import Any

import numpy as np

from nexora_audio.core.processor import Processor, ProcessorKind
from nexora_audio.utils.audio_utils import Float32Array


class GainProcessor(Processor):
    name = "test-gain"

    def __init__(self, gain: float, rate: int = 48000, frame: int = 480) -> None:
        self.gain, self._rate, self._frame = np.float32(gain), rate, frame
        self.closed = False

    @property
    def native_sample_rate(self) -> int:
        return self._rate

    @property
    def native_frame_size(self) -> int:
        return self._frame

    def process(self, frame: Float32Array) -> Float32Array:
        assert frame.shape[1] == self._frame
        return frame * self.gain

    def close(self) -> None:
        self.closed = True


class DelayProcessor(Processor):
    """Pure delay line of ``delay`` samples; reports it as latency."""

    name = "test-delay"

    def __init__(self, delay: int, rate: int, frame: int, channels: int = 1) -> None:
        self._delay, self._rate, self._frame = delay, rate, frame
        self._mem = np.zeros((channels, delay), dtype=np.float32)

    @property
    def native_sample_rate(self) -> int:
        return self._rate

    @property
    def native_frame_size(self) -> int:
        return self._frame

    @property
    def latency_samples(self) -> int:
        return self._delay

    @property
    def max_channels(self) -> int:
        return self._mem.shape[0]

    def process(self, frame: Float32Array) -> Float32Array:
        buf = np.concatenate([self._mem, frame], axis=1)
        self._mem = buf[:, buf.shape[1] - self._delay :].copy() if self._delay else self._mem
        return buf[:, : self._frame].copy()

    def reset(self) -> None:
        self._mem[:] = 0


class EnergyAnalyzer(Processor):
    """Analysis processor recording RMS per frame."""

    name = "test-energy"
    kind = ProcessorKind.ANALYSIS

    def __init__(self, rate: int = 16000, frame: int = 512) -> None:
        self._rate, self._frame = rate, frame
        self._pending: list[dict[str, Any]] = []

    @property
    def native_sample_rate(self) -> int:
        return self._rate

    @property
    def native_frame_size(self) -> int:
        return self._frame

    def process(self, frame: Float32Array) -> Float32Array:
        self._pending.append({"rms": float(np.sqrt(np.mean(frame**2)))})
        return frame

    def pop_results(self) -> list[dict[str, Any]]:
        out, self._pending = self._pending, []
        return out


def sine(freq: float, rate: int, seconds: float, amp: float = 0.5) -> Float32Array:
    t = np.arange(int(rate * seconds)) / rate
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)[None, :]


def feed_in_chunks(fn: Any, x: Float32Array, sizes: list[int]) -> Float32Array:
    outs, i, k = [], 0, 0
    while i < x.shape[1]:
        n = sizes[k % len(sizes)]
        outs.append(fn(x[:, i : i + n]))
        i, k = i + n, k + 1
    return np.concatenate(outs, axis=1)
