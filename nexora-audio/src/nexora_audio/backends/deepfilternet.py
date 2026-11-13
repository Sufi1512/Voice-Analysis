"""DeepFilterNet3 noise suppression (Hendrik Schröter, MIT OR Apache-2.0).

Uses libDF's C API (``libdf``) built from https://github.com/Rikorose/DeepFilterNet
and the official ``DeepFilterNet3_onnx.tar.gz`` model. Runs at 48 kHz on 10 ms
(480-sample) hops, one model state per channel.

DeepFilterNet estimates gains on a fine spectral scale plus "deep filter"
coefficients, so unlike RNNoise it can remove noise *under* the voice instead of
only between words.

Speech gating (default): a Silero VAD :class:`SpeechDetector` runs on the input.
DeepFilterNet's own 30 ms delay acts as look-ahead, so the decision is ready before
the matching audio is output.

* speech present: attenuation is capped at ``speech_atten_lim_db`` so quiet parts
  of words are never removed (measured: unlimited DFN3 cut ~31-35% of speech frames)
* no speech: no cap, plus a smooth extra ``pause_gate_db`` gate, because DFN3 lets
  bursts of low-frequency noise through in pauses (measured: -11 to -24 dB on pink noise)
"""

from __future__ import annotations

import ctypes
import os
import platform
import threading
from pathlib import Path

import numpy as np

from nexora_audio.backends.silero import SpeechDetector
from nexora_audio.config import NexoraConfig
from nexora_audio.core.capabilities import BackendSpec
from nexora_audio.core.processor import Processor
from nexora_audio.exceptions import BackendError
from nexora_audio.utils.audio_utils import Float32Array

LIB_ENV_VAR = "NEXORA_DEEPFILTER_LIBRARY"
MODEL_ENV_VAR = "NEXORA_DEEPFILTER_MODEL"
SAMPLE_RATE = 48000
FRAME_SIZE = 480
# Measured end-to-end delay (STFT window + 2-frame model look-ahead);
# checked by tests/integration/test_deepfilternet.py on real speech.
LATENCY_SAMPLES = 1440
# pause gate: closes over ~200 ms after the detector's hangover; opens instantly
_GATE_RELEASE = np.float32(1.0 - np.exp(-FRAME_SIZE / (0.2 * SAMPLE_RATE)))

_PKG = Path(__file__).resolve().parent.parent
_FloatPtr = ctypes.POINTER(ctypes.c_float)
_lock = threading.Lock()
_lib: ctypes.CDLL | None = None


def _platform_tag() -> str:
    machine = platform.machine().lower()
    machine = {"amd64": "x86_64", "arm64": "aarch64"}.get(machine, machine)
    return f"{platform.system().lower()}-{machine}"


def library_candidates() -> list[str]:
    paths = [p for p in [os.environ.get(LIB_ENV_VAR)] if p]
    name = {"linux": "libdf.so", "darwin": "libdf.dylib", "windows": "df.dll"}.get(
        platform.system().lower()
    )
    if name:
        paths.append(str(_PKG / "_native" / _platform_tag() / name))
    return paths


def model_path() -> Path:
    return Path(os.environ.get(MODEL_ENV_VAR) or _PKG / "_models" / "DeepFilterNet3_onnx.tar.gz")


def _bind(lib: ctypes.CDLL) -> None:
    lib.df_create.argtypes = [ctypes.c_char_p, ctypes.c_float, ctypes.c_char_p]
    lib.df_create.restype = ctypes.c_void_p
    lib.df_get_frame_length.argtypes = [ctypes.c_void_p]
    lib.df_get_frame_length.restype = ctypes.c_size_t
    lib.df_process_frame.argtypes = [ctypes.c_void_p, _FloatPtr, _FloatPtr]
    lib.df_process_frame.restype = ctypes.c_float
    lib.df_set_atten_lim.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.df_set_atten_lim.restype = None
    lib.df_free.argtypes = [ctypes.c_void_p]
    lib.df_free.restype = None


def load_library() -> ctypes.CDLL:
    global _lib
    with _lock:
        if _lib is not None:
            return _lib
        errors = []
        for path in library_candidates():
            if not Path(path).exists():
                errors.append(f"{path}: not found")
                continue
            try:
                lib = ctypes.CDLL(path)
                _bind(lib)
            except (OSError, AttributeError) as exc:
                errors.append(f"{path}: {exc}")
                continue
            _lib = lib
            return lib
        tried = "; ".join(errors) or "no candidate paths for this platform"
        raise BackendError(
            f"libdf not available for {_platform_tag()} ({tried}). Set {LIB_ENV_VAR} to a "
            "libdf built from https://github.com/Rikorose/DeepFilterNet with --features capi."
        )


def probe() -> str | None:
    if not model_path().exists():
        return f"model not found: {model_path()}"
    try:
        load_library()
    except BackendError as exc:
        return str(exc)
    return None


class DeepFilterNetProcessor(Processor):
    """DeepFilterNet3 noise suppression.

    Args:
        channels: 1 or 2 (one model state each).
        atten_lim_db: Maximum attenuation when no one is speaking (100 = no limit).
        speech_atten_lim_db: Maximum attenuation while speech is present, or ``None``
            to disable speech gating (then ``atten_lim_db`` applies throughout and no
            pause gate is used).
        pause_gate_db: Extra attenuation in pauses (0 to disable).
    """

    name = "deepfilternet3"

    def __init__(
        self,
        channels: int = 1,
        atten_lim_db: float = 100.0,
        speech_atten_lim_db: float | None = None,
        pause_gate_db: float = 0.0,
    ) -> None:
        if channels not in (1, 2):
            raise BackendError("DeepFilterNet backend supports 1 or 2 channels")
        if atten_lim_db <= 0 or (speech_atten_lim_db is not None and speech_atten_lim_db <= 0):
            raise BackendError("attenuation limits must be positive")
        if pause_gate_db < 0:
            raise BackendError("pause_gate_db must be >= 0")
        problem = probe()
        if problem:
            raise BackendError(problem)
        self._lib = load_library()
        self._channels = channels
        path = str(model_path()).encode()
        self._states: list[int] = []
        for _ in range(channels):
            # libDF aborts the process on load errors, so the path is checked by probe() above
            st = self._lib.df_create(path, ctypes.c_float(atten_lim_db), None)
            if not st:
                self.close()
                raise BackendError("df_create failed")
            if self._lib.df_get_frame_length(st) != FRAME_SIZE:
                self._states.append(st)
                self.close()
                raise BackendError("unexpected DeepFilterNet frame length")
            self._states.append(st)
        self.atten_lim_db = atten_lim_db
        self.speech_atten_lim_db = speech_atten_lim_db
        self._detector = SpeechDetector(SAMPLE_RATE) if speech_atten_lim_db is not None else None
        self._pause_gain = np.float32(10 ** (-pause_gate_db / 20)) if self._detector else 1.0
        self._gain = np.float32(self._pause_gain)
        self._lim_now = atten_lim_db
        self._ramp = np.arange(1, FRAME_SIZE + 1, dtype=np.float32) / np.float32(FRAME_SIZE)
        self._in = np.empty(FRAME_SIZE, dtype=np.float32)
        self._out = np.empty(FRAME_SIZE, dtype=np.float32)
        self._in_ptr = self._in.ctypes.data_as(_FloatPtr)
        self._out_ptr = self._out.ctypes.data_as(_FloatPtr)
        self.local_snr_db = np.zeros(channels, dtype=np.float32)

    @property
    def native_sample_rate(self) -> int:
        return SAMPLE_RATE

    @property
    def native_frame_size(self) -> int:
        return FRAME_SIZE

    @property
    def latency_samples(self) -> int:
        return LATENCY_SAMPLES

    @property
    def max_channels(self) -> int:
        return self._channels

    def set_atten_lim(self, db: float) -> None:
        for st in self._states:
            self._lib.df_set_atten_lim(st, ctypes.c_float(db))
        self.atten_lim_db = db

    def process(self, frame: Float32Array) -> Float32Array:
        if not self._states:
            raise BackendError("processor is closed")
        speech = False
        if self._detector is not None:
            mono = frame.mean(axis=0, keepdims=True) if frame.shape[0] > 1 else frame
            speech = self._detector.push(mono)
            assert self.speech_atten_lim_db is not None
            lim = self.speech_atten_lim_db if speech else self.atten_lim_db
            if lim != self._lim_now:
                for st in self._states:
                    self._lib.df_set_atten_lim(st, ctypes.c_float(lim))
                self._lim_now = lim
        out = np.empty_like(frame)
        for ch, st in enumerate(self._states):
            self._in[:] = frame[ch]
            self.local_snr_db[ch] = self._lib.df_process_frame(st, self._in_ptr, self._out_ptr)
            out[ch] = self._out
        if self._detector is None or self._pause_gain >= 1.0:
            return out
        target = np.float32(1.0) if speech else np.float32(self._pause_gain)
        prev = self._gain
        new = target if target > prev else prev + (target - prev) * _GATE_RELEASE
        self._gain = np.float32(new)
        if prev == new == 1.0:
            return out
        gated: Float32Array = (out * (prev + (new - prev) * self._ramp)).astype(np.float32)
        return gated

    @property
    def speech_active(self) -> bool:
        return bool(self._detector is not None and self._detector.speech)

    def reset(self) -> None:
        if not self._states:
            return
        path = str(model_path()).encode()
        for i, st in enumerate(self._states):
            self._lib.df_free(st)
            self._states[i] = self._lib.df_create(path, ctypes.c_float(self.atten_lim_db), None)
        self._lim_now = self.atten_lim_db
        self._gain = np.float32(self._pause_gain)
        if self._detector is not None:
            self._detector.reset()

    def close(self) -> None:
        for st in self._states:
            self._lib.df_free(st)
        self._states = []

    def __del__(self) -> None:
        if getattr(self, "_states", None):
            self.close()


def _factory(config: NexoraConfig) -> Processor:
    return DeepFilterNetProcessor(
        config.channels,
        atten_lim_db=config.deepfilter_atten_lim_db,
        speech_atten_lim_db=(
            min(config.deepfilter_speech_atten_lim_db, config.deepfilter_atten_lim_db)
            if config.speech_protection
            else None
        ),
        pause_gate_db=config.pause_gate_db if config.speech_protection else 0.0,
    )


SPEC = BackendSpec(
    feature="noise_cancellation",
    name="deepfilternet3",
    probe=probe,
    factory=_factory,
    priority=20,  # preferred over RNNoise when available
)
