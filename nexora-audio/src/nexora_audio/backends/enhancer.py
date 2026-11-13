"""Voice enhancement and automatic gain control (pure DSP, no model, zero latency).

Chain (each stage optional):

1. High-pass filter at 80 Hz: removes rumble, handling noise and hum below the voice.
2. Clarity EQ: peaking boost around 3 kHz, where consonant detail lives.
3. Speech leveler (AGC): moves the speech level towards a target. Gain only
   changes on frames detected as speech (above a tracked noise floor), so pauses
   and background noise are never pumped up.
4. Peak limiter: keeps peaks under -1 dBFS so the output never clips.

Gains change sample by sample within each frame to avoid clicks. Stereo channels
share one gain so the stereo image is preserved.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, sosfilt, sosfilt_zi

from nexora_audio.config import NexoraConfig
from nexora_audio.core.capabilities import BackendSpec
from nexora_audio.core.processor import Processor
from nexora_audio.exceptions import BackendError
from nexora_audio.utils.audio_utils import Float32Array

SAMPLE_RATE = 48000
FRAME_SIZE = 480
_FRAME_S = FRAME_SIZE / SAMPLE_RATE


def _peaking_sos(freq: float, gain_db: float, q: float, rate: int) -> np.ndarray:
    """RBJ audio-EQ-cookbook peaking filter as one second-order section."""
    a = 10 ** (gain_db / 40)
    w0 = 2 * np.pi * freq / rate
    alpha = np.sin(w0) / (2 * q)
    b = np.array([1 + alpha * a, -2 * np.cos(w0), 1 - alpha * a])
    den = np.array([1 + alpha / a, -2 * np.cos(w0), 1 - alpha / a])
    return np.concatenate([b / den[0], den / den[0]])[None, :]


def _coef(time_s: float) -> float:
    """One-pole smoothing coefficient per frame for a given time constant."""
    return float(1.0 - np.exp(-_FRAME_S / time_s))


class VoiceEnhancer(Processor):
    """High-pass + clarity EQ + speech leveler + peak limiter.

    Args:
        channels: 1 or 2.
        highpass_hz: High-pass cutoff, or ``None`` to skip.
        clarity_db: Presence boost at 3 kHz in dB (0 to skip).
        agc_target_dbfs: Target speech RMS level, or ``None`` to disable levelling.
        max_gain_db / min_gain_db: Limits for the leveler gain.
        ceiling_dbfs: Peak limiter ceiling, or ``None`` to disable.
        attack_s / release_s: Leveler time constants for lowering / raising gain.
        speech_margin_db: How far above the tracked noise floor a frame must be
            to count as speech (only speech frames move the gain).
    """

    def __init__(
        self,
        channels: int = 1,
        *,
        highpass_hz: float | None = 80.0,
        clarity_db: float = 3.0,
        agc_target_dbfs: float | None = -20.0,
        max_gain_db: float = 15.0,
        min_gain_db: float = -10.0,
        ceiling_dbfs: float | None = -1.0,
        attack_s: float = 0.4,
        release_s: float = 2.5,
        speech_margin_db: float = 12.0,
        name: str = "voice-enhancer",
    ) -> None:
        if channels not in (1, 2):
            raise BackendError("voice enhancer supports 1 or 2 channels")
        self.name = name
        self._channels = channels
        sections = []
        if highpass_hz:
            sections.append(butter(2, highpass_hz, "highpass", fs=SAMPLE_RATE, output="sos"))
        if clarity_db:
            sections.append(_peaking_sos(3000.0, clarity_db, 0.9, SAMPLE_RATE))
        self._sos = np.concatenate(sections) if sections else None
        self._zi_unit = sosfilt_zi(self._sos) if self._sos is not None else None
        self.agc_target_dbfs = agc_target_dbfs
        self.max_gain_db, self.min_gain_db = max_gain_db, min_gain_db
        self._ceiling = None if ceiling_dbfs is None else float(10 ** (ceiling_dbfs / 20))
        # Slow on purpose: the leveler follows the talker's overall loudness, not
        # individual syllables. Fast settings (50 ms / 0.6 s) flattened speech and
        # cost ~0.07 STOI in testing (docs, section 8). The peak limiter handles fast peaks.
        self._attack = _coef(attack_s)
        self._release = _coef(release_s)
        self._speech_margin_db = speech_margin_db
        self._ramp = (np.arange(1, FRAME_SIZE + 1, dtype=np.float32) / FRAME_SIZE)[None, :]
        self.reset()

    @property
    def native_sample_rate(self) -> int:
        return SAMPLE_RATE

    @property
    def native_frame_size(self) -> int:
        return FRAME_SIZE

    @property
    def max_channels(self) -> int:
        return self._channels

    @property
    def gain_db(self) -> float:
        """Current leveler gain in dB."""
        return self._gain_db

    def reset(self) -> None:
        self._zi = (
            np.zeros((self._channels, *self._zi_unit.shape)) if self._zi_unit is not None else None
        )
        self._gain_db = 0.0
        self._applied = 1.0  # linear gain at the end of the previous frame
        self._floor_db: float | None = None  # set from the first frame heard

    def process(self, frame: Float32Array) -> Float32Array:
        x = frame
        if self._sos is not None and self._zi is not None:
            x = np.empty_like(frame)
            for ch in range(frame.shape[0]):
                y, self._zi[ch] = sosfilt(self._sos, frame[ch], zi=self._zi[ch])
                x[ch] = y

        target = 10 ** (self._gain_db / 20)
        if self.agc_target_dbfs is not None:
            target = self._level(x)
        if self._ceiling is not None:  # limiter: this frame's peak must fit the ceiling
            peak = float(np.max(np.abs(x))) * target
            if peak > self._ceiling:
                target *= self._ceiling / peak
        g = self._applied + (target - self._applied) * self._ramp
        self._applied = target
        out = (x * g).astype(np.float32)
        if self._ceiling is not None:  # ramp start may still overshoot slightly
            np.clip(out, -self._ceiling, self._ceiling, out=out)
        return out

    def _level(self, x: Float32Array) -> float:
        """Update the leveler from this frame; return the linear gain to reach."""
        rms = float(np.sqrt(np.mean(np.square(x, dtype=np.float64))))
        level = 20 * np.log10(rms) if rms > 1e-9 else -120.0
        # noise floor: follows quieter frames immediately, creeps up ~3 dB/s otherwise,
        # so steady noise is recognised as noise and never boosted
        if self._floor_db is None:
            self._floor_db = level
        self._floor_db = min(level, self._floor_db + 3.0 * _FRAME_S)
        speech = level > -60.0 and level > self._floor_db + self._speech_margin_db
        if speech:
            assert self.agc_target_dbfs is not None
            wanted = np.clip(self.agc_target_dbfs - level, self.min_gain_db, self.max_gain_db)
            k = self._attack if wanted < self._gain_db else self._release
            self._gain_db += (float(wanted) - self._gain_db) * k
        return float(10 ** (self._gain_db / 20))


def _enhancer_factory(config: NexoraConfig) -> Processor:
    return VoiceEnhancer(
        config.channels,
        clarity_db=config.clarity_db,
        agc_target_dbfs=config.agc_target_dbfs if config.auto_gain_control else None,
    )


def _agc_factory(config: NexoraConfig) -> Processor:
    return VoiceEnhancer(
        config.channels,
        highpass_hz=None,
        clarity_db=0.0,
        agc_target_dbfs=config.agc_target_dbfs,
        name="agc",
    )


def _always() -> str | None:
    return None


ENHANCER_SPEC = BackendSpec("voice_enhancement", "voice-enhancer", _always, _enhancer_factory)
AGC_SPEC = BackendSpec("auto_gain_control", "agc", _always, _agc_factory)
