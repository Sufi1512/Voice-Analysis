"""Stateful streaming polyphase resampler.

Unlike :func:`scipy.signal.resample_poly`, which treats every call as an
isolated signal, this keeps filter history between calls. Processing a stream
in chunks of any size gives the same output as processing it in one piece.
"""

from __future__ import annotations

from math import gcd

import numpy as np
from scipy.signal import firwin

from nexora_audio.exceptions import AudioFormatError
from nexora_audio.utils.audio_utils import Float32Array


class StreamingResampler:
    """Rational-ratio resampler (``out_rate / in_rate = up / down``).

    The anti-aliasing filter is a Kaiser-windowed FIR (``beta=8.6``, about 80 dB
    stopband attenuation) with cutoff at the lower Nyquist frequency.

    Args:
        in_rate: Input sample rate in Hz.
        out_rate: Output sample rate in Hz.
        channels: Number of channels.
        half_len: Filter half-length in units of the larger of ``up``/``down``.
            Larger means a sharper filter, more delay and more CPU.
    """

    def __init__(
        self, in_rate: int, out_rate: int, channels: int, *, half_len: int = 16, beta: float = 8.6
    ) -> None:
        if in_rate <= 0 or out_rate <= 0 or channels <= 0:
            raise ValueError("rates and channels must be positive")
        g = gcd(in_rate, out_rate)
        self.in_rate, self.out_rate, self.channels = in_rate, out_rate, channels
        self.up, self.down = out_rate // g, in_rate // g
        self.passthrough = self.up == self.down == 1
        if self.passthrough:
            self._poly = np.ones((1, 1), dtype=np.float32)
            self._k = self._n_taps = 1
            self.reset()
            return

        max_rate = max(self.up, self.down)
        n_taps = 2 * half_len * max_rate + 1
        taps = firwin(n_taps, 1.0 / max_rate, window=("kaiser", beta)) * self.up
        k = -(-n_taps // self.up)  # taps per polyphase branch
        padded = np.zeros(k * self.up)
        padded[:n_taps] = taps
        # _poly[p, j] multiplies x[i - j] for output phase p
        self._poly = padded.reshape(k, self.up).T.astype(np.float32).copy()
        self._k = k
        self._n_taps = n_taps
        self.reset()

    @property
    def delay_out_samples(self) -> float:
        """Group delay of the filter, in output samples (may be fractional)."""
        if self.passthrough:
            return 0.0
        return (self._n_taps - 1) / 2.0 / self.down

    @property
    def delay_seconds(self) -> float:
        return self.delay_out_samples / self.out_rate

    def reset(self) -> None:
        self._hist: Float32Array = np.zeros((self.channels, self._k - 1), dtype=np.float32)
        self._x_offset = -(self._k - 1)  # global input index of _hist[:, 0]
        self._next_j = 0  # upsampled-domain index of the next output sample

    def process(self, chunk: Float32Array) -> Float32Array:
        """Resample a ``(channels, n)`` chunk; returns every output sample now computable."""
        if chunk.ndim != 2 or chunk.shape[0] != self.channels:
            raise AudioFormatError(f"expected shape ({self.channels}, n), got {chunk.shape}")
        if self.passthrough:
            return chunk

        buf = np.concatenate([self._hist, chunk.astype(np.float32, copy=False)], axis=1)
        last_index = self._x_offset + buf.shape[1] - 1
        j_max = (last_index + 1) * self.up - 1
        count = (j_max - self._next_j) // self.down + 1 if j_max >= self._next_j else 0

        if count > 0:
            js = self._next_j + self.down * np.arange(count, dtype=np.int64)
            i_local = js // self.up - self._x_offset
            idx = i_local[:, None] - np.arange(self._k, dtype=np.int64)[None, :]
            coeffs = self._poly[js % self.up]  # (count, k)
            out = np.einsum("cnk,nk->cn", buf[:, idx], coeffs, dtype=np.float32)
            self._next_j += count * self.down
        else:
            out = np.zeros((self.channels, 0), dtype=np.float32)

        keep_from = self._next_j // self.up - (self._k - 1)
        rel = max(keep_from - self._x_offset, 0)
        self._hist = buf[:, rel:].copy()
        self._x_offset += rel
        return np.ascontiguousarray(out, dtype=np.float32)

    def flush(self) -> Float32Array:
        """Push zeros through the filter to release the delayed tail of the signal."""
        if self.passthrough:
            return np.zeros((self.channels, 0), dtype=np.float32)
        pad = self._k + int(np.ceil(self.delay_out_samples * self.down / self.up)) + 1
        return self.process(np.zeros((self.channels, pad), dtype=np.float32))
