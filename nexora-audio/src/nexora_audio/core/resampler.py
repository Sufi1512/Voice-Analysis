"""Stateful streaming polyphase resampler.

Unlike :func:`scipy.signal.resample_poly`, which treats every call as an
isolated signal, this keeps filter history between calls. Processing a stream
in chunks of any size gives the same output as processing it in one piece.
"""

from __future__ import annotations

from math import gcd

import numpy as np
from scipy.signal import firwin, lfilter

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
        self,
        in_rate: int,
        out_rate: int,
        channels: int,
        *,
        half_len: int = 16,
        beta: float = 8.6,
        fast: bool = True,
    ) -> None:
        self.fast = fast
        if in_rate <= 0 or out_rate <= 0 or channels <= 0:
            raise ValueError("rates and channels must be positive")
        g = gcd(in_rate, out_rate)
        self.in_rate, self.out_rate, self.channels = in_rate, out_rate, channels
        self.up, self.down = out_rate // g, in_rate // g
        self.passthrough = self.up == self.down == 1
        if self.passthrough:
            self._poly = np.ones((1, 1), dtype=np.float32)
            self._poly64 = self._poly.astype(np.float64)
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
        self._poly64 = self._poly.astype(np.float64)
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

    @property
    def _integer_ratio(self) -> bool:
        return not self.passthrough and (self.up == 1 or self.down == 1)

    def reset(self) -> None:
        self._hist: Float32Array = np.zeros((self.channels, self._k - 1), dtype=np.float32)
        self._x_offset = -(self._k - 1)  # global input index of _hist[:, 0]
        self._next_j = 0  # upsampled-domain index of the next output sample
        # fast path state (integer ratios): one FIR state per polyphase branch
        self._zi = np.zeros((self.up, self.channels, self._k - 1), dtype=np.float64)
        self._consumed = 0  # input samples seen (decimation phase)

    def _process_integer(self, x: Float32Array) -> Float32Array:
        """Integer up- or down-sampling with SciPy's compiled FIR filter.

        Computes exactly the same samples as the general path (tested), much faster.
        """
        if self.down == 1:  # upsample by L: branch p gives outputs L*i + p
            out = np.empty((self.channels, x.shape[1] * self.up), dtype=np.float32)
            for p in range(self.up):
                y, self._zi[p] = lfilter(self._poly64[p], [1.0], x, axis=1, zi=self._zi[p])
                out[:, p :: self.up] = y
            return out
        # downsample by M: full-rate FIR, keep samples whose global index is a multiple of M
        y, self._zi[0] = lfilter(self._poly64[0], [1.0], x, axis=1, zi=self._zi[0])
        first = (-self._consumed) % self.down
        self._consumed += x.shape[1]
        return np.ascontiguousarray(y[:, first :: self.down], dtype=np.float32)

    def process(self, chunk: Float32Array) -> Float32Array:
        """Resample a ``(channels, n)`` chunk; returns every output sample now computable."""
        if chunk.ndim != 2 or chunk.shape[0] != self.channels:
            raise AudioFormatError(f"expected shape ({self.channels}, n), got {chunk.shape}")
        if self.passthrough:
            return chunk
        if self._integer_ratio and self.fast:
            if chunk.shape[1] == 0:
                return np.zeros((self.channels, 0), dtype=np.float32)
            return self._process_integer(chunk)

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
