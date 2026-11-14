"""Background-talker gate: speech much quieter than the caller is background, not the caller.

A voice detector says "speech" for any voice: the caller, but also a TV, colleagues in a
call centre, an airport announcement. The quality lab measured what that costs: with
babble, TV or announcements behind the caller, pauses stayed only 4-24 dB quieter and the
background switched on and off (up to 21 dB of pumping).

Over a single microphone the clearest difference is level: the caller is close to the
microphone, background talkers are far away. The gate follows the caller's level (80th
percentile of the cleaned speech level over the last 4 s of speech it accepted) and calls
any "speech" more than ``margin_db`` below it background. Default 17 dB, chosen on the lab:
15 dB cut slightly more of the caller's quiet speech, 20 dB lost most of the benefit.
If for 8 s only background has been heard, it accepts that voice as the new speaker (a
quieter caller must not stay silenced).

It does not separate a background talker as loud as the caller: that needs a model of the
caller's voice (phase E11). (Tried and rejected: judging only when the caller is clearly
above the input floor. It undid most of the babble improvement; the one case it changed was
TV noise at -5 dB SNR, where transcription is garbage with or without the gate.)
"""

from __future__ import annotations

import numpy as np

_HISTORY = 400  # 4 s of 10 ms frames
_MIN_HISTORY = 100  # 1 s of accepted speech before judging anything
_TAKEOVER = 800  # 8 s of background only: accept it as the speaker


class TalkerGate:
    def __init__(self, frame_s: float, margin_db: float = 17.0) -> None:
        self.margin = 10 ** (-margin_db / 10)
        steps = max(1, round(0.01 / frame_s))  # history counts 10 ms frames
        self._attack = 0.5
        # slow release (falls 17 dB in ~0.6 s): faster cut soft speech (lab: phone worst
        # case 3.7% -> 8.2%)
        self._release = float(np.exp(-frame_s / 0.15))
        self._steps = steps
        self.reset()

    def reset(self) -> None:
        self._env = 0.0
        self._hist = np.zeros(_HISTORY)
        self._n = 0
        self._ref = 0.0
        self._bg_run = 0
        self.background_frames = 0

    @property
    def ready(self) -> bool:
        return self._n >= _MIN_HISTORY

    def update(self, energy: float, speech: bool) -> bool:
        """Feed one frame's cleaned energy and the detector's verdict.
        Returns True when the frame is background speech."""
        a = self._attack if energy > self._env else 1 - self._release
        self._env += a * (energy - self._env)
        if not speech:
            return False
        background = self.ready and self._env < self._ref * self.margin
        if background:
            self._bg_run += 1
            self.background_frames += 1
            if self._bg_run < _TAKEOVER:
                return True
            self._n = 0  # the background has become the speaker: relearn
        self._bg_run = 0
        self._hist[self._n % _HISTORY] = self._env
        self._n += 1
        if self._n % 10 == 0 or self._n == _MIN_HISTORY:
            self._ref = float(np.percentile(self._hist[: min(self._n, _HISTORY)], 80))
        return False
