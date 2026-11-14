"""Opus (RFC 6716) decoding and encoding through the system ``libopus`` (BSD-3).

Opus is packet-based: every :meth:`OpusDecoder.decode` call takes exactly one packet
(one WebSocket message). An empty packet means "this packet was lost": the decoder's
own concealment produces audio for it, at the length of the previous packet.

The library is found with ``ctypes.util.find_library("opus")`` (Debian/Ubuntu package
``libopus0``, macOS ``brew install opus``) or the path in ``NEXORA_OPUS_LIBRARY``.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import threading

import numpy as np

from nexora_audio.exceptions import AudioFormatError, BackendError
from nexora_audio.utils.audio_utils import Float32Array

LIB_ENV_VAR = "NEXORA_OPUS_LIBRARY"
RATES = (8000, 12000, 16000, 24000, 48000)
APPLICATION_VOIP = 2048
_MAX_FRAME_S = 0.12  # longest Opus packet: 120 ms
_lock = threading.Lock()
_lib: ctypes.CDLL | None = None
_FloatPtr = ctypes.POINTER(ctypes.c_float)
_BytePtr = ctypes.POINTER(ctypes.c_ubyte)


def load_library() -> ctypes.CDLL:
    global _lib
    with _lock:
        if _lib is not None:
            return _lib
        path = os.environ.get(LIB_ENV_VAR) or ctypes.util.find_library("opus")
        if not path:
            raise BackendError(
                f"libopus not found: install it (e.g. apt install libopus0) or set {LIB_ENV_VAR}"
            )
        try:
            lib = ctypes.CDLL(path)
        except OSError as exc:
            raise BackendError(f"cannot load libopus from {path}: {exc}") from exc
        i32p = ctypes.POINTER(ctypes.c_int)
        lib.opus_decoder_create.argtypes = [ctypes.c_int32, ctypes.c_int, i32p]
        lib.opus_decoder_create.restype = ctypes.c_void_p
        lib.opus_decode_float.argtypes = [
            ctypes.c_void_p,
            _BytePtr,
            ctypes.c_int32,
            _FloatPtr,
            ctypes.c_int,
            ctypes.c_int,
        ]
        lib.opus_decode_float.restype = ctypes.c_int
        lib.opus_decoder_destroy.argtypes = [ctypes.c_void_p]
        lib.opus_decoder_destroy.restype = None
        lib.opus_encoder_create.argtypes = [ctypes.c_int32, ctypes.c_int, ctypes.c_int, i32p]
        lib.opus_encoder_create.restype = ctypes.c_void_p
        lib.opus_encode_float.argtypes = [
            ctypes.c_void_p,
            _FloatPtr,
            ctypes.c_int,
            _BytePtr,
            ctypes.c_int32,
        ]
        lib.opus_encode_float.restype = ctypes.c_int32
        lib.opus_encoder_destroy.argtypes = [ctypes.c_void_p]
        lib.opus_encoder_destroy.restype = None
        lib.opus_strerror.argtypes = [ctypes.c_int]
        lib.opus_strerror.restype = ctypes.c_char_p
        lib.opus_get_version_string.restype = ctypes.c_char_p
        _lib = lib
        return lib


def probe() -> str | None:
    try:
        load_library()
    except BackendError as exc:
        return str(exc)
    return None


def version() -> str:
    return str(load_library().opus_get_version_string().decode())


def _check_rate(rate: int, channels: int) -> None:
    if rate not in RATES:
        raise AudioFormatError(f"Opus sample_rate must be one of {RATES}, got {rate}")
    if channels not in (1, 2):
        raise AudioFormatError("Opus supports 1 or 2 channels")


class OpusDecoder:
    def __init__(self, rate: int, channels: int = 1) -> None:
        _check_rate(rate, channels)
        self._lib = load_library()
        err = ctypes.c_int(0)
        self._st = self._lib.opus_decoder_create(rate, channels, ctypes.byref(err))
        if not self._st or err.value != 0:
            raise BackendError(f"opus_decoder_create failed: {err.value}")
        self.rate, self.channels = rate, channels
        self._max = int(_MAX_FRAME_S * rate)
        self._buf = np.zeros(self._max * channels, np.float32)
        self._last = rate // 50  # 20 ms until the first packet tells us
        self.lost_packets = 0

    def decode(self, packet: bytes) -> Float32Array:
        """One packet to planar float32 ``(channels, n)``; ``b""`` = lost packet."""
        out = self._buf.ctypes.data_as(_FloatPtr)
        if packet:
            data = (ctypes.c_ubyte * len(packet)).from_buffer_copy(packet)
            n = self._lib.opus_decode_float(self._st, data, len(packet), out, self._max, 0)
        else:
            self.lost_packets += 1
            n = self._lib.opus_decode_float(self._st, None, 0, out, self._last, 0)
        if n < 0:
            raise AudioFormatError(f"Opus decode failed: {self._lib.opus_strerror(n).decode()}")
        if packet:
            self._last = n
        x = self._buf[: n * self.channels].reshape(n, self.channels).T
        return np.ascontiguousarray(x, dtype=np.float32)

    def reset(self) -> None:
        self.close()
        self.__init__(self.rate, self.channels)  # type: ignore[misc]

    def close(self) -> None:
        if getattr(self, "_st", None):
            self._lib.opus_decoder_destroy(self._st)
            self._st = None

    def __del__(self) -> None:
        self.close()


class OpusEncoder:
    """Encoder for clients and tests: planar float32 frames of 2.5-60 ms to packets."""

    def __init__(self, rate: int, channels: int = 1, application: int = APPLICATION_VOIP) -> None:
        _check_rate(rate, channels)
        self._lib = load_library()
        err = ctypes.c_int(0)
        self._st = self._lib.opus_encoder_create(rate, channels, application, ctypes.byref(err))
        if not self._st or err.value != 0:
            raise BackendError(f"opus_encoder_create failed: {err.value}")
        self.rate, self.channels = rate, channels
        self._out = (ctypes.c_ubyte * 4000)()

    def encode(self, planar: Float32Array) -> bytes:
        frame = np.ascontiguousarray(planar.T.reshape(-1), dtype=np.float32)
        n = planar.shape[1]
        size = self._lib.opus_encode_float(
            self._st, frame.ctypes.data_as(_FloatPtr), n, self._out, len(self._out)
        )
        if size < 0:
            raise AudioFormatError(f"Opus encode failed: {self._lib.opus_strerror(size).decode()}")
        return bytes(self._out[:size])

    def close(self) -> None:
        if getattr(self, "_st", None):
            self._lib.opus_encoder_destroy(self._st)
            self._st = None

    def __del__(self) -> None:
        self.close()
