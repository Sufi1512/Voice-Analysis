"""Silero VAD (MIT) through ONNX Runtime, without PyTorch.

Two uses:

* :class:`SpeechDetector`: a small helper that noise-cancellation backends feed
  with their own frames to know when someone is speaking (used for speech-gated
  suppression).
* :class:`SileroVADProcessor`: the public ``vad`` feature, an analysis processor
  that reports per-window speech probability and speech start/end events.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import numpy as np

from nexora_audio.config import NexoraConfig
from nexora_audio.core.capabilities import BackendSpec
from nexora_audio.core.processor import Processor, ProcessorKind
from nexora_audio.core.reframer import Reframer
from nexora_audio.core.resampler import StreamingResampler
from nexora_audio.exceptions import BackendError
from nexora_audio.utils.audio_utils import Float32Array

MODEL_PATH = Path(__file__).resolve().parent.parent / "_models" / "silero_vad.onnx"
SAMPLE_RATE = 16000
WINDOW = 512  # 32 ms
_CONTEXT = 64

_session_lock = threading.Lock()


def probe() -> str | None:
    try:
        import onnxruntime  # noqa: F401
    except ImportError:
        return "onnxruntime is not installed"
    if not MODEL_PATH.exists():
        return f"model file missing: {MODEL_PATH}"
    return None


class SileroVAD:
    """Stateful Silero VAD on 16 kHz mono, 512-sample windows."""

    def __init__(self) -> None:
        problem = probe()
        if problem:
            raise BackendError(f"Silero VAD unavailable: {problem}")
        import onnxruntime as ort

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 1  # one small model: threads only add jitter
        opts.inter_op_num_threads = 1
        with _session_lock:
            self._session = ort.InferenceSession(
                str(MODEL_PATH), opts, providers=["CPUExecutionProvider"]
            )
        self._sr = np.array(SAMPLE_RATE, dtype=np.int64)
        self._buf = np.zeros((1, _CONTEXT + WINDOW), dtype=np.float32)
        self.reset()

    def reset(self) -> None:
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._buf[:] = 0.0

    def __call__(self, window: Float32Array) -> float:
        """Speech probability (0..1) for one 512-sample window."""
        self._buf[0, _CONTEXT:] = window
        prob, self._state = self._session.run(
            None, {"input": self._buf, "state": self._state, "sr": self._sr}
        )
        self._buf[0, :_CONTEXT] = self._buf[0, -_CONTEXT:]
        return float(prob[0, 0])


class SpeechDetector:
    """Speech / no-speech decision for a stream at ``in_rate``, with hysteresis.

    Speech starts when the probability reaches ``threshold`` and ends after it has
    stayed below ``threshold - 0.15`` for ``hangover_s``.
    """

    def __init__(
        self, in_rate: int = 48000, threshold: float = 0.5, hangover_s: float = 0.3
    ) -> None:
        self._vad = SileroVAD()
        self._resampler = StreamingResampler(in_rate, SAMPLE_RATE, 1)
        self._reframer = Reframer(1, WINDOW)
        self._window = np.empty((1, WINDOW), dtype=np.float32)
        self.threshold = threshold
        self._off = max(threshold - 0.15, 0.05)
        self._hangover = hangover_s
        self.reset()

    def reset(self) -> None:
        self._vad.reset()
        self._resampler.reset()
        self._reframer.reset()
        self.speech = False
        self.probability = 0.0
        self._quiet_s = 0.0

    def push(self, mono: Float32Array) -> bool:
        """Feed ``(1, n)`` audio; returns the current decision."""
        self._reframer.push(self._resampler.process(mono))
        while self._reframer.pop(self._window) is not None:
            p = self._vad(self._window[0])
            self.probability = p
            if p >= self.threshold:
                self.speech, self._quiet_s = True, 0.0
            elif p < self._off and self.speech:
                self._quiet_s += WINDOW / SAMPLE_RATE
                if self._quiet_s >= self._hangover:
                    self.speech = False
        return self.speech


class SileroVADProcessor(Processor):
    """Public VAD feature: probability per 32 ms window plus start/end events.

    Each result has ``probability`` and ``speech`` (bool), and ``event`` set to
    ``"speech_start"`` or ``"speech_end"`` on transitions.
    """

    name = "silero-vad"
    kind = ProcessorKind.ANALYSIS

    def __init__(self, threshold: float = 0.5, hangover_s: float = 0.3) -> None:
        self._vad = SileroVAD()
        self.threshold = threshold
        self._off = max(threshold - 0.15, 0.05)
        self._hangover = hangover_s
        self._pending: list[dict[str, Any]] = []
        self._speech = False
        self._quiet_s = 0.0

    @property
    def native_sample_rate(self) -> int:
        return SAMPLE_RATE

    @property
    def native_frame_size(self) -> int:
        return WINDOW

    def process(self, frame: Float32Array) -> Float32Array:
        p = self._vad(frame[0])
        event = None
        if p >= self.threshold:
            self._quiet_s = 0.0
            if not self._speech:
                self._speech, event = True, "speech_start"
        elif p < self._off and self._speech:
            self._quiet_s += WINDOW / SAMPLE_RATE
            if self._quiet_s >= self._hangover:
                self._speech, event = False, "speech_end"
        self._pending.append({"probability": p, "speech": self._speech, "event": event})
        return frame

    def pop_results(self) -> list[dict[str, Any]]:
        out, self._pending = self._pending, []
        return out

    def reset(self) -> None:
        self._vad.reset()
        self._speech = False
        self._quiet_s = 0.0
        self._pending = []


def _factory(config: NexoraConfig) -> Processor:
    return SileroVADProcessor(threshold=config.vad_threshold)


SPEC = BackendSpec(feature="vad", name="silero-vad", probe=probe, factory=_factory)
