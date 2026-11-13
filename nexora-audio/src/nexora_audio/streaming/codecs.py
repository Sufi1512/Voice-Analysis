"""Byte-level audio formats for network streams.

Supported encodings, all little-endian and interleaved:

* ``pcm16``: signed 16-bit PCM, the usual format for WebRTC, browsers and STT/TTS APIs
* ``float32``: 32-bit float in [-1, 1]
* ``mulaw`` / ``alaw``: 8-bit G.711, used by telephony (Twilio, SIP), usually 8 kHz mono

The G.711 code is a NumPy implementation of the ITU-T formulas, because
``audioop`` was removed from the standard library in Python 3.13.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from nexora_audio.exceptions import AudioFormatError
from nexora_audio.utils.audio_utils import Float32Array

Encoding = Literal["pcm16", "float32", "mulaw", "alaw"]
_BYTES = {"pcm16": 2, "float32": 4, "mulaw": 1, "alaw": 1}


@dataclass(frozen=True, slots=True)
class AudioFormat:
    """Wire format of a byte stream."""

    encoding: Encoding = "pcm16"
    sample_rate: int = 16000
    channels: int = 1

    def __post_init__(self) -> None:
        if self.encoding not in _BYTES:
            raise AudioFormatError(f"unsupported encoding {self.encoding!r}")
        if self.channels not in (1, 2):
            raise AudioFormatError("channels must be 1 or 2")
        if not 8000 <= self.sample_rate <= 192000:
            raise AudioFormatError(f"sample_rate {self.sample_rate} out of range")

    @property
    def bytes_per_frame(self) -> int:
        """Bytes per sample across all channels."""
        return _BYTES[self.encoding] * self.channels

    def bytes_for_ms(self, ms: float) -> int:
        return round(self.sample_rate * ms / 1000.0) * self.bytes_per_frame


# ---- G.711 -----------------------------------------------------------------

_MU_BIAS = 0x84
_MU_CLIP = 32635


def _mulaw_decode_table() -> np.ndarray:
    u = ~np.arange(256, dtype=np.int32) & 0xFF
    sign = u & 0x80
    exponent = (u >> 4) & 0x07
    mantissa = u & 0x0F
    mag = (((mantissa << 3) + _MU_BIAS) << exponent) - _MU_BIAS
    return np.where(sign != 0, -mag, mag).astype(np.int16)


def _alaw_decode_table() -> np.ndarray:
    a = np.arange(256, dtype=np.int32) ^ 0x55
    sign = a & 0x80
    exponent = (a >> 4) & 0x07
    mantissa = a & 0x0F
    mag = np.where(exponent == 0, (mantissa << 4) + 8, ((mantissa << 4) + 0x108) << (exponent - 1))
    return np.where(sign != 0, mag, -mag).astype(np.int16)


_MU_DECODE = _mulaw_decode_table()
_A_DECODE = _alaw_decode_table()


def mulaw_encode(pcm: np.ndarray) -> np.ndarray:
    """int16 samples to G.711 μ-law bytes (uint8)."""
    # ITU-T G.711 reference: work on 14-bit values (arithmetic shift first)
    x = pcm.astype(np.int32) >> 2
    sign = np.where(x < 0, 0x80, 0)
    mag = np.minimum(np.where(x < 0, -x, x), _MU_CLIP >> 2) + (_MU_BIAS >> 2)
    exponent = np.clip(np.floor(np.log2(mag)).astype(np.int32) - 5, 0, 7)
    mantissa = (mag >> (exponent + 1)) & 0x0F
    out: np.ndarray = (~(sign | (exponent << 4) | mantissa) & 0xFF).astype(np.uint8)
    return out


def alaw_encode(pcm: np.ndarray) -> np.ndarray:
    """int16 samples to G.711 A-law bytes (uint8)."""
    x = pcm.astype(np.int32) >> 3  # 13-bit
    sign = np.where(x >= 0, 0x80, 0)
    mag = np.where(x >= 0, x, -x - 1)
    mag = np.minimum(mag, 0xFFF)
    exponent = np.where(mag < 32, 0, np.floor(np.log2(np.maximum(mag, 1))).astype(np.int32) - 4)
    exponent = np.clip(exponent, 0, 7)
    mantissa = np.where(exponent == 0, mag >> 1, mag >> exponent) & 0x0F
    out: np.ndarray = ((sign | (exponent << 4) | mantissa) ^ 0x55).astype(np.uint8)
    return out


def mulaw_decode(data: np.ndarray) -> np.ndarray:
    out: np.ndarray = _MU_DECODE[data]
    return out


def alaw_decode(data: np.ndarray) -> np.ndarray:
    out: np.ndarray = _A_DECODE[data]
    return out


# ---- stream decoder / encoder ------------------------------------------------


class StreamDecoder:
    """Bytes to planar float32, keeping incomplete trailing bytes for the next call."""

    def __init__(self, fmt: AudioFormat) -> None:
        self.format = fmt
        self._pending = b""

    def decode(self, data: bytes) -> Float32Array:
        buf = self._pending + data
        usable = len(buf) - len(buf) % self.format.bytes_per_frame
        self._pending = buf[usable:]
        raw = buf[:usable]
        enc, ch = self.format.encoding, self.format.channels
        if enc == "pcm16":
            x = np.frombuffer(raw, dtype="<i2").astype(np.float32) / np.float32(32768.0)
        elif enc == "float32":
            x = np.frombuffer(raw, dtype="<f4").astype(np.float32)
            if x.size and not np.isfinite(x).all():
                raise AudioFormatError("float32 stream contains NaN or infinite values")
        elif enc == "mulaw":
            x = mulaw_decode(np.frombuffer(raw, dtype=np.uint8)).astype(np.float32) / 32768.0
        else:
            x = alaw_decode(np.frombuffer(raw, dtype=np.uint8)).astype(np.float32) / 32768.0
        return np.ascontiguousarray(x.reshape(-1, ch).T, dtype=np.float32)

    def reset(self) -> None:
        self._pending = b""


def encode(planar: Float32Array, fmt: AudioFormat) -> bytes:
    """Planar float32 to bytes in ``fmt`` (clipped to full scale)."""
    x = np.clip(planar.T.reshape(-1), -1.0, 1.0)
    if fmt.encoding == "float32":
        return x.astype("<f4").tobytes()
    pcm = np.clip(np.round(x * 32768.0), -32768, 32767).astype(np.int16)
    if fmt.encoding == "pcm16":
        return pcm.astype("<i2").tobytes()
    if fmt.encoding == "mulaw":
        return mulaw_encode(pcm).tobytes()
    return alaw_encode(pcm).tobytes()
