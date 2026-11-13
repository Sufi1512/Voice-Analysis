"""RNNoise noise-suppression backend (xiph.org RNNoise, BSD-3-Clause).

Runs at 48 kHz on 10 ms (480-sample) frames, one denoiser state per channel.
The pipeline converts other rates and chunk sizes.
"""

from __future__ import annotations

import ctypes
import ctypes.util
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

ENV_VAR = "NEXORA_RNNOISE_LIBRARY"
SAMPLE_RATE = 48000
FRAME_SIZE = 480
# Measured end-to-end delay of RNNoise v0.2 (output lags input by two frames).
# tests/integration/test_rnnoise.py checks this against real speech.
LATENCY_SAMPLES = 960
_SCALE = np.float32(32768.0)
_RN_ONSET = 0.6  # RNNoise speech probability that opens the gate at word onsets
_RELEASE = np.float32(1.0 - np.exp(-FRAME_SIZE / (0.15 * SAMPLE_RATE)))

_FloatPtr = ctypes.POINTER(ctypes.c_float)
_lib_lock = threading.Lock()
_lib: ctypes.CDLL | None = None
_lib_path: str | None = None


def _platform_tag() -> str:
    machine = platform.machine().lower()
    machine = {"amd64": "x86_64", "arm64": "aarch64"}.get(machine, machine)
    return f"{platform.system().lower()}-{machine}"


def candidate_paths() -> list[str]:
    """Library locations tried, in order: env var, bundled binary, system library."""
    paths: list[str] = []
    if env := os.environ.get(ENV_VAR):
        paths.append(env)
    names = {"linux": "librnnoise.so", "darwin": "librnnoise.dylib", "windows": "rnnoise.dll"}
    name = names.get(platform.system().lower())
    if name:
        bundled = Path(__file__).resolve().parent.parent / "_native" / _platform_tag() / name
        paths.append(str(bundled))
    system = ctypes.util.find_library("rnnoise")
    if system:
        paths.append(system)
    return paths


def _bind(lib: ctypes.CDLL) -> None:
    lib.rnnoise_create.argtypes = [ctypes.c_void_p]
    lib.rnnoise_create.restype = ctypes.c_void_p
    lib.rnnoise_destroy.argtypes = [ctypes.c_void_p]
    lib.rnnoise_destroy.restype = None
    lib.rnnoise_get_frame_size.argtypes = []
    lib.rnnoise_get_frame_size.restype = ctypes.c_int
    lib.rnnoise_process_frame.argtypes = [ctypes.c_void_p, _FloatPtr, _FloatPtr]
    lib.rnnoise_process_frame.restype = ctypes.c_float


def load_library() -> tuple[ctypes.CDLL, str]:
    """Load librnnoise once per process. Raises BackendError listing every path tried."""
    global _lib, _lib_path
    with _lib_lock:
        if _lib is not None and _lib_path is not None:
            return _lib, _lib_path
        errors: list[str] = []
        for path in candidate_paths():
            if os.sep in path and not Path(path).exists():
                errors.append(f"{path}: not found")
                continue
            try:
                lib = ctypes.CDLL(path)
                _bind(lib)
                if lib.rnnoise_get_frame_size() != FRAME_SIZE:
                    errors.append(f"{path}: unexpected frame size")
                    continue
            except (OSError, AttributeError) as exc:
                errors.append(f"{path}: {exc}")
                continue
            _lib, _lib_path = lib, path
            return lib, path
        tried = "; ".join(errors) or "no candidate paths for this platform"
        raise BackendError(
            f"librnnoise not available for {_platform_tag()} ({tried}). "
            f"Set {ENV_VAR} to a librnnoise built from https://github.com/xiph/rnnoise."
        )


def probe() -> str | None:
    try:
        load_library()
    except BackendError as exc:
        return str(exc)
    return None


class RNNoiseProcessor(Processor):
    """Noise suppression with RNNoise and speech-gated protection.

    Full-strength RNNoise removes noise in pauses almost completely, but in strong
    noise it also removes quiet parts of words, which sounds like the voice cutting
    out. With ``speech_strength`` set, a Silero VAD speech detector runs alongside:

    * no speech: suppression is ``strength`` (default 1.0, so pauses are clean)
    * speech: suppression is ``speech_strength`` (e.g. 0.85 caps it at ~16.5 dB),
      blending a little delay-aligned original back in so weak syllables survive.

    RNNoise's own per-frame speech probability also opens the gate, because it
    reacts faster at word onsets. The mix ramps sample by sample and releases over
    ~150 ms after Silero's 300 ms hangover, so it doesn't click or pump.

    Args:
        channels: 1 or 2. Each channel gets its own denoiser state.
        strength: Suppression when no one is speaking, 0..1 (1.0 = fully denoised).
        speech_strength: Suppression while speech is present, or ``None`` to apply
            ``strength`` all the time (no speech detector).
    """

    name = "rnnoise"

    def __init__(
        self, channels: int = 1, strength: float = 1.0, speech_strength: float | None = None
    ) -> None:
        if channels not in (1, 2):
            raise BackendError("RNNoise backend supports 1 or 2 channels")
        if not 0.0 <= strength <= 1.0:
            raise BackendError("strength must be within [0, 1]")
        if speech_strength is not None and not 0.0 <= speech_strength <= 1.0:
            raise BackendError("speech_strength must be within [0, 1]")
        self._detector: SpeechDetector | None = None
        if speech_strength is not None and speech_strength < strength:
            self._detector = SpeechDetector(SAMPLE_RATE)
        self.speech_strength = np.float32(
            strength if speech_strength is None else min(speech_strength, strength)
        )
        self._mix = np.float32(strength)
        self._ramp = np.arange(1, FRAME_SIZE + 1, dtype=np.float32) / np.float32(FRAME_SIZE)
        self._rn_speech = np.zeros(LATENCY_SAMPLES // FRAME_SIZE + 1, dtype=bool)
        self._lib, self.library_path = load_library()
        self._channels = channels
        self.strength = np.float32(strength)
        self._states: list[int] = []
        for _ in range(channels):
            st = self._lib.rnnoise_create(None)
            if not st:
                self.close()
                raise BackendError("rnnoise_create failed")
            self._states.append(st)
        self._in = np.empty(FRAME_SIZE, dtype=np.float32)
        self._out = np.empty(FRAME_SIZE, dtype=np.float32)
        self._in_ptr = self._in.ctypes.data_as(_FloatPtr)
        self._out_ptr = self._out.ctypes.data_as(_FloatPtr)
        # history of the original signal, used to align the dry path for strength < 1
        self._dry = np.zeros((channels, LATENCY_SAMPLES + FRAME_SIZE), dtype=np.float32)
        self.speech_probability = np.zeros(channels, dtype=np.float32)

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

    def process(self, frame: Float32Array) -> Float32Array:
        if not self._states:
            raise BackendError("processor is closed")
        out = np.empty_like(frame)
        for ch, st in enumerate(self._states):
            np.multiply(frame[ch], _SCALE, out=self._in)
            prob = self._lib.rnnoise_process_frame(st, self._out_ptr, self._in_ptr)
            self.speech_probability[ch] = prob
            np.divide(self._out, _SCALE, out=out[ch])
        self._dry[:, :LATENCY_SAMPLES] = self._dry[:, FRAME_SIZE:]
        self._dry[:, LATENCY_SAMPLES:] = frame
        dry = self._dry[:, :FRAME_SIZE]

        if self._detector is None:
            if self.strength >= 1.0:
                return out
            return self.strength * out + (np.float32(1.0) - self.strength) * dry

        mono = frame.mean(axis=0, keepdims=True) if frame.shape[0] > 1 else frame
        silero = self._detector.push(mono)
        # RNNoise's probability belongs to the input frame; output lags by 2 frames,
        # so the last 3 values cover the output frame plus 20 ms of look-ahead
        self._rn_speech[:-1] = self._rn_speech[1:]
        self._rn_speech[-1] = bool(np.max(self.speech_probability) >= _RN_ONSET)
        speech = silero or bool(self._rn_speech.any())
        target = self.speech_strength if speech else self.strength
        prev = self._mix
        new = target if target < prev else prev + (target - prev) * _RELEASE
        self._mix = np.float32(new)
        if prev >= 1.0 and new >= 1.0:
            return out
        g = prev + (new - prev) * self._ramp
        return g * out + (np.float32(1.0) - g) * dry

    @property
    def speech_active(self) -> bool:
        """Whether the speech gate is currently open (always False without a detector)."""
        return bool(self._mix < self.strength)

    def reset(self) -> None:
        if not self._states:
            return
        for i, st in enumerate(self._states):
            self._lib.rnnoise_destroy(st)
            self._states[i] = self._lib.rnnoise_create(None)
        self._dry[:] = 0.0
        self.speech_probability[:] = 0.0
        self._rn_speech[:] = False
        self._mix = np.float32(self.strength)
        if self._detector is not None:
            self._detector.reset()

    def close(self) -> None:
        for st in self._states:
            self._lib.rnnoise_destroy(st)
        self._states = []

    def __del__(self) -> None:
        if getattr(self, "_states", None):
            self.close()


def _factory(config: NexoraConfig) -> Processor:
    return RNNoiseProcessor(
        config.channels,
        config.noise_cancellation_strength,
        speech_strength=(
            min(config.speech_protection_strength, config.noise_cancellation_strength)
            if config.speech_protection
            else None
        ),
    )


SPEC = BackendSpec(
    feature="noise_cancellation", name="rnnoise", probe=probe, factory=_factory, priority=10
)
