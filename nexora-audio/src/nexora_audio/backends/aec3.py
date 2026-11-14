"""Acoustic echo cancellation with WebRTC AEC3 (Google, BSD-3).

Uses ``libnexora_aec``: a small C API over WebRTC AudioProcessing v2.1, built from the
``webrtc-audio-processing`` crate's bundled source (see ``_native/PROVENANCE.md``). Only
the echo canceller is enabled; noise removal and gain stay in our own pipeline.

The canceller needs the far-end signal: the agent audio played to the caller. A
:class:`~nexora_audio.streaming.session.StreamSession` feeds it with
``push_reference()``; the processor keeps it on its own sample timeline as a playout
queue and gives AEC3 the reference frame for each microphone frame. AEC3 estimates the
remaining echo delay itself (phone paths add hundreds of milliseconds).

Runs first in the pipeline, at the stream's own rate when AEC3 supports it (8, 16, 32 or
48 kHz), before noise removal: a noise model in front would change the echo and stop
the canceller from matching it.

Two protections for the caller's voice (quality lab, before them: 11-50% of caller speech
cut while both talk, 39-45% with a headset where there is no echo at all):

* a near-transparent suppressor tuning (:data:`DEFAULT_TUNING`);
* headset bypass: an :class:`~nexora_audio.streaming.echo.EchoGate` on the same frames
  detects when no echo path exists after 1.5 s of agent speech, and the caller's audio
  then passes through untouched (re-checked continuously).
"""

from __future__ import annotations

import ctypes
import math
import os
import platform
import threading
from pathlib import Path

import numpy as np

from nexora_audio.config import NexoraConfig
from nexora_audio.core.capabilities import BackendSpec
from nexora_audio.core.processor import Processor
from nexora_audio.exceptions import BackendError
from nexora_audio.streaming.echo import EchoGate, ReferenceTimeline
from nexora_audio.utils.audio_utils import Float32Array

LIB_ENV_VAR = "NEXORA_AEC_LIBRARY"
RATES = (8000, 16000, 32000, 48000)
_PKG = Path(__file__).resolve().parent.parent
_FloatPtr = ctypes.POINTER(ctypes.c_float)
_lock = threading.Lock()
_lib: ctypes.CDLL | None = None

# AEC3 tuning values understood by nexora_aec_create_tuned (order matters; NaN = default).
TUNING_KEYS = (
    "ep_default_gain",
    "ep_default_len",
    "normal_lf_enr_transparent",
    "normal_lf_enr_suppress",
    "normal_hf_enr_transparent",
    "normal_hf_enr_suppress",
    "nearend_enr_threshold",
    "nearend_snr_threshold",
    "nearend_hold_duration",
    "nearend_trigger_threshold",
    "nearend_lf_enr_transparent",
    "nearend_lf_enr_suppress",
)
# Near-transparent suppressor: AEC3's defaults assume an echo exists until its filter has
# converged, and cut the caller by 20-48 dB while the agent talks even with no echo at all
# (quality lab, headset case); in double-talk they cut ~30% of the caller's speech. These
# masks let the suppressor act only where echo clearly dominates; the linear filter does
# the rest. Lab (harsh synthetic speakerphone echo): echo removed 20-22 dB instead of 37-46,
# caller speech cut in double-talk 11% instead of 30%.
DEFAULT_TUNING: dict[str, float] = {
    "normal_lf_enr_transparent": 5.0,
    "normal_lf_enr_suppress": 10.0,
    "normal_hf_enr_transparent": 5.0,
    "normal_hf_enr_suppress": 10.0,
    "nearend_lf_enr_transparent": 10.0,
    "nearend_lf_enr_suppress": 20.0,
}


def _platform_tag() -> str:
    machine = platform.machine().lower()
    machine = {"amd64": "x86_64", "arm64": "aarch64"}.get(machine, machine)
    return f"{platform.system().lower()}-{machine}"


def library_candidates() -> list[str]:
    paths = [p for p in [os.environ.get(LIB_ENV_VAR)] if p]
    name = {"linux": "libnexora_aec.so", "darwin": "libnexora_aec.dylib"}.get(
        platform.system().lower()
    )
    if name:
        paths.append(str(_PKG / "_native" / _platform_tag() / name))
    return paths


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
                lib.nexora_aec_create.argtypes = [ctypes.c_uint32, ctypes.c_int32]
                lib.nexora_aec_create.restype = ctypes.c_void_p
                lib.nexora_aec_create_tuned.argtypes = [ctypes.c_uint32, ctypes.c_int32, _FloatPtr]
                lib.nexora_aec_create_tuned.restype = ctypes.c_void_p
                lib.nexora_aec_frame_size.argtypes = [ctypes.c_void_p]
                lib.nexora_aec_frame_size.restype = ctypes.c_size_t
                lib.nexora_aec_render.argtypes = [ctypes.c_void_p, _FloatPtr]
                lib.nexora_aec_render.restype = ctypes.c_int32
                lib.nexora_aec_capture.argtypes = [ctypes.c_void_p, _FloatPtr]
                lib.nexora_aec_capture.restype = ctypes.c_int32
                lib.nexora_aec_stats.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_double)]
                lib.nexora_aec_stats.restype = ctypes.c_int32
                lib.nexora_aec_destroy.argtypes = [ctypes.c_void_p]
                lib.nexora_aec_destroy.restype = None
            except (OSError, AttributeError) as exc:
                errors.append(f"{path}: {exc}")
                continue
            _lib = lib
            return lib
        raise BackendError(
            f"libnexora_aec not available for {_platform_tag()} "
            f"({'; '.join(errors) or 'no candidate paths'}). Set {LIB_ENV_VAR}."
        )


def probe() -> str | None:
    try:
        load_library()
    except BackendError as exc:
        return str(exc)
    return None


class AEC3Processor(Processor):
    """WebRTC AEC3 echo canceller for one mono stream.

    Args:
        rate: Processing rate (8000, 16000, 32000 or 48000).
        stream_delay_ms: Known echo delay, or ``None`` to let AEC3 estimate it.
        guard_margin_db: ``None`` disables the headset bypass (any number enables it).
    """

    name = "webrtc-aec3"

    def __init__(
        self,
        rate: int = 16000,
        stream_delay_ms: int | None = None,
        guard_margin_db: float | None = 6.0,
        tuning: dict[str, float] | None = None,
    ) -> None:
        if rate not in RATES:
            raise BackendError(f"AEC3 runs at {RATES} Hz, not {rate}")
        self._lib = load_library()
        self._delay = -1 if stream_delay_ms is None else int(stream_delay_ms)
        self.rate = rate
        self._tuning = np.full(len(TUNING_KEYS), np.nan, np.float32)
        for k, v in {**DEFAULT_TUNING, **(tuning or {})}.items():
            self._tuning[TUNING_KEYS.index(k)] = v
        self._st = self._create()
        if not self._st:
            raise BackendError("nexora_aec_create failed")
        self._n = int(self._lib.nexora_aec_frame_size(self._st))
        self.reference = ReferenceTimeline(rate)
        self._pos = 0  # samples of microphone audio processed (timeline position)
        self._frame = np.zeros(self._n, np.float32)
        self._ref = np.zeros(self._n, np.float32)
        self._stats = (ctypes.c_double * 4)()
        self._gate = EchoGate(rate) if guard_margin_db is not None else None
        self._margin = 10 ** (-(guard_margin_db or 0.0) / 10)
        self._mic = np.zeros(self._n, np.float32)
        self._beta = 0.0
        self._ramp = np.arange(1, self._n + 1, dtype=np.float32) / np.float32(self._n)
        self.guarded_frames = 0

    def _create(self) -> int | None:
        ptr = self._tuning.ctypes.data_as(_FloatPtr)
        st: int | None = self._lib.nexora_aec_create_tuned(self.rate, self._delay, ptr)
        return st

    @property
    def native_sample_rate(self) -> int:
        return self.rate

    @property
    def native_frame_size(self) -> int:
        return self._n

    @property
    def max_channels(self) -> int:
        return 1

    def push_reference(self, x: Float32Array) -> None:
        """Agent audio (mono, at ``rate``) sent to the caller now."""
        self.reference.push(x, self._pos)

    def process(self, frame: Float32Array) -> Float32Array:
        if not self._st:
            raise BackendError("processor is closed")
        self._ref[:] = self.reference.get(self._pos, self._n)
        self._lib.nexora_aec_render(self._st, self._ref.ctypes.data_as(_FloatPtr))
        self._frame[:] = frame[0]
        self._mic[:] = frame[0]
        self._lib.nexora_aec_capture(self._st, self._frame.ctypes.data_as(_FloatPtr))
        self._pos += self._n
        if self._gate is not None:
            self._guard()
        return self._frame[None, :].copy()

    def _guard(self) -> None:
        """No echo path (a headset, or the device cancels echo itself): pass the caller
        through untouched, crossfading over 10 ms."""
        assert self._gate is not None
        g = self._gate
        g.update(self._mic, self._ref)
        new = 1.0 if g.no_echo else 0.0
        prev = self._beta
        self._beta = new
        if prev == 0.0 and new == 0.0:
            return
        self.guarded_frames += int(new > 0)
        w = prev + (new - prev) * self._ramp
        self._frame[:] = w * self._mic + (1 - w) * self._frame

    def stats(self) -> dict[str, float | None]:
        """Echo canceller statistics for the last frame (``None`` where unknown)."""
        self._lib.nexora_aec_stats(self._st, self._stats)
        names = ("erle_db", "erl_db", "delay_ms", "residual_echo_likelihood")
        return {
            k: (None if math.isnan(v) else round(v, 2))
            for k, v in zip(names, self._stats, strict=True)
        }

    def reset(self) -> None:
        self.close()
        self._st = self._create()
        self.reference.reset()
        self._pos = 0
        self._beta = 0.0
        if self._gate is not None:
            self._gate.reset()

    def close(self) -> None:
        if getattr(self, "_st", None):
            self._lib.nexora_aec_destroy(self._st)
            self._st = None

    def __del__(self) -> None:
        self.close()


def _factory(config: NexoraConfig) -> Processor:
    rate = config.sample_rate if config.sample_rate in RATES else 48000
    return AEC3Processor(rate)


SPEC = BackendSpec(
    feature="echo_cancellation",
    name="webrtc-aec3",
    probe=probe,
    factory=_factory,
    priority=10,
)
