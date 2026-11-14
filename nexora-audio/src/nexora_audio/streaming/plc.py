"""Packet-loss concealment (PLC) for one mono stream.

Missing audio usually reaches us as digital silence (jitter buffers and gateways fill
lost packets with zeros). Fed to the noise model and VAD, those holes become clicks,
broken words and a speech detector that resets mid-word.

This concealer works like ITU-T G.711 Appendix I (waveform substitution):

* estimate the pitch period from the last 30 ms (66-400 Hz) by normalised
  autocorrelation;
* repeat the most recent pitch period (two after 10 ms, three after 20 ms, so a long
  gap does not buzz);
* keep full level for the first 10 ms, then fade 20% per 10 ms: silent after 60 ms;
* when real audio returns, crossfade into it over 4 ms.

A loss is *detected* when at least 2.5 ms of exact zeros follow audible signal (above
-60 dBFS over the last 10 ms), or *signalled* with :meth:`LossConcealer.conceal`.
The start of a stream and real silence after the 60 ms fade are left untouched.

A detected gap only counts as a loss (``events``, ``concealed_samples``) once real audio
resumes within 200 ms; a longer run of zeros is a mute or the end of speech, whose only
trace is a 60 ms fade.
"""

from __future__ import annotations

from itertools import pairwise

import numpy as np

from nexora_audio.utils.audio_utils import Float32Array

_HISTORY_S = 0.05
_FULL_S = 0.010  # no fade during the first 10 ms
_FADE_END_S = 0.060  # silent after 60 ms
_XFADE_S = 0.004
_MIN_RUN_S = 0.0025
_MAX_LOSS_S = 0.2  # longer zero runs are mutes, not lost packets
_AUDIBLE = 10 ** (-60 / 10)


class LossConcealer:
    def __init__(self, rate: int, silence_level: float = 0.0) -> None:
        self.rate = rate
        self.silence_level = silence_level  # A-law silence decodes to +-8/32768, not 0
        self._hist_n = int(_HISTORY_S * rate)
        self._min_run = max(1, int(_MIN_RUN_S * rate))
        self._xfade = max(1, int(_XFADE_S * rate))
        self._lo_lag = max(2, rate // 400)
        self._hi_lag = rate // 66
        self.reset()

    def reset(self) -> None:
        self._hist = np.zeros(self._hist_n, np.float32)
        self._filled = 0
        self._lost = 0  # samples concealed in the current gap (0: not in a gap)
        self._period = 0
        self._phase = 0
        self._zero_carry = 0
        self._gap = 0  # concealed samples in the current gap, not yet counted
        self._signalled = False
        self._concealed = 0
        self._events = 0

    @property
    def concealed_samples(self) -> int:
        """Samples concealed in gaps that were losses (see the module notes)."""
        return self._concealed + (self._gap if self._signalled else 0)

    @property
    def events(self) -> int:
        return self._events + int(self._signalled and self._lost > 0)

    # -- helpers -----------------------------------------------------------------

    def _push_history(self, x: Float32Array) -> None:
        if len(x) >= self._hist_n:
            self._hist[:] = x[-self._hist_n :]
        else:
            self._hist[: -len(x)] = self._hist[len(x) :]
            self._hist[-len(x) :] = x
        self._filled = min(self._hist_n, self._filled + len(x))

    def _audible(self) -> bool:
        n = self.rate // 100
        if self._filled < n:
            return False
        return float(np.mean(self._hist[-n:].astype(np.float64) ** 2)) > _AUDIBLE

    def _pitch(self) -> int:
        seg = self._hist[-int(0.03 * self.rate) :].astype(np.float64)
        best, best_lag = -1.0, self._hi_lag
        n = len(seg)
        for lag in range(self._lo_lag, min(self._hi_lag, n // 2) + 1):
            a, b = seg[lag:], seg[: n - lag]
            den = np.sqrt(np.dot(a, a) * np.dot(b, b)) + 1e-12
            c = float(np.dot(a, b) / den)
            if c > best:
                best, best_lag = c, lag
        return best_lag

    def _synth(self, n: int) -> Float32Array:
        """Next ``n`` concealment samples (continues the current gap)."""
        if self._lost == 0:
            self._period = self._pitch()
            self._phase = 0
        out = np.empty(n, np.float32)
        full = int(_FULL_S * self.rate)
        end = int(_FADE_END_S * self.rate)
        for i in range(n):
            t = self._lost + i
            periods = 1 if t < full else (2 if t < 2 * full else 3)
            span = min(periods * self._period, self._filled)
            src = self._hist[-span + (self._phase % span)]
            self._phase += 1
            gain = 1.0 if t < full else max(0.0, 1.0 - 0.2 * (t - full) / full)
            out[i] = src * gain if t < end else 0.0
        self._gap += max(0, min(n, end - self._lost))
        self._lost += n
        return out

    def _recover(self, x: Float32Array) -> Float32Array:
        """Crossfade from the concealment into real audio after a gap."""
        if self._lost == 0:
            return x
        if self._signalled or self._lost <= _MAX_LOSS_S * self.rate:
            self._concealed += self._gap
            self._events += 1
        n = min(self._xfade, len(x))
        if self._lost < int(_FADE_END_S * self.rate):
            tail = self._synth(n)  # crossfade only: not counted
            w = (np.arange(1, n + 1, dtype=np.float32) / (n + 1)).astype(np.float32)
            x = x.copy()
            x[:n] = w * x[:n] + (1 - w) * tail
        self._lost, self._gap, self._signalled = 0, 0, False
        return x

    # -- public API --------------------------------------------------------------

    def conceal(self, n: int) -> Float32Array:
        """Audio for ``n`` samples the transport knows are missing."""
        if self._filled == 0:
            return np.zeros(n, np.float32)
        self._signalled = True
        return self._synth(n)

    def process(self, x: Float32Array) -> Float32Array:
        """Return ``x`` with detected loss gaps (runs of exact zeros) concealed."""
        if len(x) == 0:
            return x
        zero = np.abs(x) <= self.silence_level
        if not zero.any() and self._lost == 0:
            self._zero_carry = 0
            self._push_history(x)
            return x
        out = x.copy()
        # split into runs of zero / non-zero samples
        edges = np.flatnonzero(np.diff(zero.astype(np.int8))) + 1
        bounds = [0, *edges.tolist(), len(x)]
        for s, e in pairwise(bounds):
            seg = x[s:e]
            if zero[s]:
                run = self._zero_carry + (e - s)
                in_gap = self._lost > 0
                if in_gap or (run >= self._min_run and self._audible()):
                    out[s:e] = self._synth(e - s)
                    self._zero_carry = run
                    continue
                self._zero_carry = run
                self._push_history(seg)
            else:
                self._zero_carry = 0
                out[s:e] = self._recover(seg)
                self._push_history(seg)
        return out
