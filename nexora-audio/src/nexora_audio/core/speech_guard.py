"""Speech guard: a noise suppressor may never remove more than the noise can explain.

If a frame's input energy is ``E`` and the noise floor is ``N``, the speech in it has
about ``E - N`` energy. A correct suppressor outputs roughly that. When the model
outputs much less, it is removing speech (measured: DeepFilterNet3 removes 14-65% of
speech frames on clean 8 kHz phone audio, and the VAD-gated pause gate removes whole
utterances when the VAD misses speech at -5 dB SNR).

The guard runs after the model on the same frames:

* tracks the noise floor of the (latency-aligned) input: it follows dips down at once,
  rises at most ``floor_rise_db_s`` (3 dB/s) so it never climbs into continuous speech,
  and is lifted to the lowest smoothed energy of the last ``floor_window_s`` (4 s) so it
  catches up within 4 s when noise starts after silence;
* in frames above the floor (by about 1.6 dB) *and* plausibly speech (VAD probability
  at least ``min_probability``, default 0.35, the detector's own "speech has ended"
  level), it requires the output to keep at least ``(E - N)`` minus ``margin_db``, and
  restores any shortfall by blending back the aligned input;
* reports whether it was active, so the caller can keep its pause gate open.

Noise-only frames sit at the floor, so they are never protected and pauses stay clean.
Loud non-speech bursts (doors, clicks) have a low VAD probability and are not protected.
"""

from __future__ import annotations

from collections import deque

import numpy as np

from nexora_audio.utils.audio_utils import Float32Array

_EPS = 1e-12
_FLOOR_MIN = 1e-10  # -100 dBFS: the floor never sits at digital zero, so it can rise


class SpeechGuard:
    """Per-frame guard for one mono stream (frames of fixed length).

    Args:
        frame_size: Samples per frame.
        frame_s: Frame duration in seconds.
        latency: Samples between a model's input and its matching output.
        margin_db: Extra removal allowed beyond the noise share.
        min_probability: VAD probability needed to treat a frame as possible speech.
        floor_rise_db_s: Fastest rise of the noise floor during sound, dB per second.
        floor_window_s: Sliding-minimum window that bounds how far the floor can lag.
    """

    def __init__(
        self,
        frame_size: int,
        frame_s: float,
        latency: int,
        margin_db: float = 6.0,
        min_probability: float = 0.35,
        floor_rise_db_s: float = 3.0,
        floor_window_s: float = 4.0,
    ) -> None:
        self.frame_size = frame_size
        self.latency = latency
        self.margin = 10 ** (-margin_db / 10)
        self.min_probability = min_probability
        self._rise = 10 ** (floor_rise_db_s * frame_s / 10)
        self._block = max(1, round(0.1 / frame_s))  # 100 ms sub-blocks
        self._blocks = max(2, round(floor_window_s / (self._block * frame_s)))
        self._release = np.exp(-frame_s / 0.05)  # blend fades over ~50 ms
        self._ramp = np.arange(1, frame_size + 1, dtype=np.float32) / np.float32(frame_size)
        self.reset()

    def reset(self) -> None:
        self._delay = np.zeros(self.latency + self.frame_size, dtype=np.float32)
        self._smooth = 0.0
        self.noise_floor = -1.0  # unknown until the first frame
        self._tracked = -1.0
        self._warmup = -(-self.latency // self.frame_size)  # frames before input is aligned
        self._mins: deque[float] = deque(maxlen=self._blocks)
        self._cur_min = np.inf
        self._count = 0
        self._beta = 0.0
        self.active = False
        self.restored_frames = 0

    def _aligned_input(self, frame: Float32Array) -> Float32Array:
        n, lat = self.frame_size, self.latency
        self._delay[lat:] = frame
        aligned = self._delay[:n].copy()
        self._delay[:lat] = self._delay[n : n + lat]
        return aligned

    def process(
        self, frame_in: Float32Array, frame_out: Float32Array, probability: float
    ) -> Float32Array:
        """``frame_in``: model input (mono, this frame); ``frame_out``: model output for
        the input ``latency`` samples earlier. Returns the guarded output."""
        x = self._aligned_input(frame_in)
        if self._warmup > 0:  # the delay line is still empty: nothing aligned to judge yet
            self._warmup -= 1
            return frame_out
        e_in = float(np.mean(x.astype(np.float64) ** 2))
        self._smooth = e_in if self.noise_floor < 0 else 0.7 * self._smooth + 0.3 * e_in
        self._cur_min = min(self._cur_min, self._smooth)
        self._count += 1
        if self._count == self._block:
            self._mins.append(self._cur_min)
            self._cur_min, self._count = np.inf, 0
        if self._tracked < 0 or self._smooth < self._tracked:
            self._tracked = max(self._smooth, _FLOOR_MIN)
        else:
            self._tracked *= self._rise
        window_min = min(self._cur_min, min(self._mins, default=np.inf))
        self.noise_floor = max(self._tracked, window_min) if len(self._mins) else self._tracked
        # minimum statistics read low (about 1 dB on steady noise): correct the bias
        floor = 1.2 * self.noise_floor + _EPS

        beta = 0.0
        self.active = probability >= self.min_probability and e_in > 1.2 * floor
        if self.active:
            target = (e_in - floor) * self.margin
            e_out = float(np.mean(frame_out.astype(np.float64) ** 2))
            if e_out < target:
                beta = min(1.0, float(np.sqrt((target - e_out) / (e_in + _EPS))))
        prev = self._beta
        new = max(beta, prev * self._release)
        self._beta = new
        if prev == 0.0 and new == 0.0:
            return frame_out
        if new > 1e-4:
            self.restored_frames += int(beta > 0)
        gain = (prev + (new - prev) * self._ramp).astype(np.float32)
        guarded: Float32Array = (frame_out + gain * x).astype(np.float32)
        return guarded
