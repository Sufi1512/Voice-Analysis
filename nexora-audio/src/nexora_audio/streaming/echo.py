"""Echo reference and echo-aware barge-in.

The agent's own voice, played on the caller's speakerphone, comes back in the caller's
audio. Without care the turn tracker hears it as the caller speaking and reports an
``interruption`` (measured: every speakerphone case in the quality lab, before E4).

:class:`ReferenceTimeline` places the agent audio the server sends to the caller on the
caller-audio timeline, as a playout queue: audio is played in real time from when it is
sent, and audio sent in bursts (TTS is usually faster than real time) queues up behind
what is still playing.

:class:`EchoGate` decides, per stretch of caller audio, whether its energy is explained
by the agent's voice coming back. It learns the echo path (delay and level) from the
envelopes of the two streams while the agent talks: the delay is the lag with the
highest correlation between the caller-audio and reference envelopes (0-600 ms), the
level is the median ratio between them. The predicted echo follows the reference
envelope with a decaying tail (rooms and speakers keep ringing after the agent's words).
A stretch is *echo* when its energy is less than ``margin_db`` above the predicted echo.
The caller talking over the agent (double-talk) adds energy the reference cannot
explain, so it still counts as speech.

Until the path is learned (about the first 0.4-1 s the agent speaks in a call), any
speech while the agent is audible is treated as possible echo: a real interruption in
that first second is reported once the path is known, a little later. If after 1.5 s of
agent speech no echo path shows up (a headset, or the device cancels echo itself), the
gate concludes there is no echo and stops filtering; it keeps checking, so it learns the
path if echo appears later (the caller switches to speakerphone).
"""

from __future__ import annotations

import numpy as np

from nexora_audio.utils.audio_utils import Float32Array

_HOP_S = 0.01
_MAX_DELAY_S = 0.6
_LEARN_S = 3.0
_MIN_LEARN_HOPS = 40  # agent speech needed before the first estimate (0.4 s)
_NO_ECHO_HOPS = 150  # 1.5 s of agent speech without an echo path: assume none
_TAIL = 0.8  # echo energy tail per 10 ms hop (about -1 dB per 10 ms)
_EPS = 1e-12


class ReferenceTimeline:
    """Agent audio on the caller-audio timeline (mono, at the caller-audio rate)."""

    def __init__(self, rate: int, keep_s: float = 10.0) -> None:
        self.rate = rate
        self._keep = int(keep_s * rate)
        self.reset()

    def reset(self) -> None:
        self._buf = np.zeros(self._keep, np.float32)
        self._start = 0  # timeline sample index of _buf[0]
        self._end = 0  # end of queued reference (timeline samples)
        self.pushed_samples = 0

    def push(self, x: Float32Array, now: int) -> None:
        """Agent audio sent at caller-timeline sample ``now`` (queued after earlier audio)."""
        if len(x) == 0:
            return
        start = max(now, self._end)
        end = start + len(x)
        self._ensure(end)
        self._buf[start - self._start : end - self._start] = x
        self._end = end
        self.pushed_samples += len(x)

    def _ensure(self, end: int) -> None:
        overflow = end - (self._start + self._keep)
        if overflow > 0:
            keep = max(0, self._keep - overflow)
            self._buf[:keep] = self._buf[self._keep - keep :]
            self._buf[keep:] = 0
            self._start += overflow

    def get(self, start: int, n: int) -> Float32Array:
        """Reference samples for timeline ``[start, start + n)`` (zeros where none)."""
        out = np.zeros(n, np.float32)
        a, b = max(start, self._start), min(start + n, self._start + self._keep)
        if b > a:
            out[a - start : b - start] = self._buf[a - self._start : b - self._start]
        return out

    @property
    def queued_until(self) -> int:
        return self._end


class EchoGate:
    """Learns the echo path from envelopes and flags caller audio that is only echo."""

    def __init__(self, rate: int, margin_db: float = 6.0) -> None:
        self.rate = rate
        self.hop = max(1, int(_HOP_S * rate))
        self.margin = 10 ** (margin_db / 10)
        self._max_lag = int(_MAX_DELAY_S / _HOP_S)
        self._learn = int(_LEARN_S / _HOP_S)
        n = self._learn + self._max_lag + 64
        self._mic = np.zeros(n)
        self._ref = np.zeros(n)
        self._env = np.zeros(n)  # reference envelope with a decaying tail
        self._n = n
        self.reset()

    def reset(self) -> None:
        self._mic[:] = 0
        self._ref[:] = 0
        self._env[:] = 0
        self._active_ref = 0  # hops with audible reference so far
        self._hops = 0  # hops seen (timeline hop index of the next one)
        self.delay_hops = -1  # unknown until learned
        self.gain = 0.0
        self.echo_hops = 0

    def update(self, mic: Float32Array, ref: Float32Array) -> None:
        """Feed one hop (10 ms) of caller audio and the aligned reference."""
        i = self._hops % self._n
        self._mic[i] = float(np.mean(mic.astype(np.float64) ** 2))
        r = float(np.mean(ref.astype(np.float64) ** 2))
        self._ref[i] = r
        self._env[i] = max(r, _TAIL * self._env[(i - 1) % self._n])
        self._active_ref += int(r > 1e-6)
        self._hops += 1
        every = 25 if self.learned else 5  # re-learn every 250 ms (50 ms until learned)
        if self._active_ref >= _MIN_LEARN_HOPS and self._hops % every == 0:
            self._learn_path()

    @property
    def learned(self) -> bool:
        return self.delay_hops >= 0

    @property
    def no_echo(self) -> bool:
        """The agent has spoken long enough and no echo path showed up (e.g. a headset)."""
        return not self.learned and self._active_ref >= _NO_ECHO_HOPS

    @property
    def current_hop(self) -> int:
        return self._hops - 1

    def _series(self, length: int, end: int, which: np.ndarray) -> np.ndarray:
        idx = (np.arange(end - length, end)) % self._n
        return which[idx]

    def _learn_path(self) -> None:
        length = min(self._learn, self._hops - 1)
        if length < _MIN_LEARN_HOPS:
            return
        mic = self._series(length, self._hops, self._mic)
        ref = self._series(length + self._max_lag, self._hops, self._env)
        if ref.max() <= _EPS:
            return
        lm = np.log10(mic + _EPS)
        # real echo paths correlate 0.83-0.92 (agent alone); chance matches with a headset
        # reach 0.61 (quality lab): require 0.7, otherwise keep the previous estimate
        best, best_lag = 0.7, -1
        for lag in range(self._max_lag + 1):
            r = ref[self._max_lag - lag : self._max_lag - lag + length]
            active = r > r.max() * 1e-3
            if active.sum() < _MIN_LEARN_HOPS // 2:
                continue
            lr = np.log10(r[active] + _EPS)
            a = lm[active]
            c = np.corrcoef(a, lr)[0, 1] if a.std() > 0 and lr.std() > 0 else 0.0
            if c > best:
                best, best_lag = c, lag
        if best_lag < 0:
            return
        r = ref[self._max_lag - best_lag : self._max_lag - best_lag + length]
        active = r > r.max() * 1e-2
        gain = float(np.median(mic[active] / (r[active] + _EPS)))
        # an "echo" quieter than the caller audio's own noise floor is a chance match
        # (background noise correlates weakly with anything): there is no echo path
        if gain * float(np.median(r[active])) < 2.0 * float(np.percentile(mic, 10)):
            self.delay_hops, self.gain = -1, 0.0
            return
        self.delay_hops = best_lag
        self.gain = gain

    def predicted_echo(self, hop_index: int) -> float:
        """Echo energy expected at timeline hop ``hop_index`` (0 if the path is unknown)."""
        if self.delay_hops < 0 or hop_index - self.delay_hops < self._hops - self._n:
            return 0.0
        j = (hop_index - self.delay_hops) % self._n
        return float(self.gain * self._env[j])

    def is_echo(self, start_s: float, dur_s: float, agent_audible: bool = True) -> bool:
        """True when the caller audio in ``[start_s, start_s + dur_s)`` is explained by echo
        (before the path is learned: whenever the agent is audible)."""
        if self.delay_hops < 0:
            undecided = 0 < self._active_ref < _NO_ECHO_HOPS
            flagged = agent_audible and undecided
            self.echo_hops += int(flagged)
            return flagged
        h0 = int(start_s / _HOP_S)
        h1 = max(h0 + 1, int((start_s + dur_s) / _HOP_S))
        if h1 > self._hops or h0 < self._hops - self._n + self._max_lag:
            return False
        mic = sum(self._mic[h % self._n] for h in range(h0, h1))
        echo = sum(self.predicted_echo(h) for h in range(h0, h1))
        flagged = echo > 0 and mic <= echo * self.margin
        self.echo_hops += int(flagged)
        return flagged
