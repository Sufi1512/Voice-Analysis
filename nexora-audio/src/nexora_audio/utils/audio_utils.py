"""Audio format helpers.

Internal convention: audio is ``float32`` in ``[-1, 1]`` with shape
``(channels, samples)`` ("planar"). Public APIs also accept the
``(samples, channels)`` layout used by soundfile and sounddevice.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray

from nexora_audio.exceptions import AudioFormatError

Float32Array = NDArray[np.float32]

_INT_SCALE = {np.dtype(np.int16): 32768.0, np.dtype(np.int32): 2147483648.0}


def to_planar_float32(
    audio: ArrayLike, channels: int | None = None, *, check_finite: bool = True
) -> Float32Array:
    """Convert user audio to planar float32 ``(channels, samples)``.

    Accepts 1-D mono arrays or 2-D ``(samples, channels)`` arrays of
    ``int16``, ``int32``, ``float32`` or ``float64``. Integer input is scaled to
    ``[-1, 1)``. If ``channels`` is given the result must have that many channels.
    """
    x = np.asarray(audio)
    if x.ndim == 1:
        x = x[np.newaxis, :]
    elif x.ndim == 2:
        x = x.T
    else:
        raise AudioFormatError(f"audio must be 1-D or 2-D (samples, channels), got shape {x.shape}")

    if x.dtype in _INT_SCALE:
        out = x.astype(np.float32) / np.float32(_INT_SCALE[x.dtype])
    elif x.dtype == np.float32:
        out = x
    elif x.dtype == np.float64:
        out = x.astype(np.float32)
    else:
        raise AudioFormatError(f"unsupported audio dtype {x.dtype}; use int16, int32 or float")

    if channels is not None and out.shape[0] != channels:
        raise AudioFormatError(f"expected {channels} channel(s), got {out.shape[0]}")
    if check_finite and out.size and not np.isfinite(out).all():
        raise AudioFormatError("audio contains NaN or infinite values")
    return np.ascontiguousarray(out)


def to_interleaved(
    planar: Float32Array, dtype: type[np.generic] = np.float32
) -> NDArray[np.generic]:
    """Convert planar float32 to ``(samples, channels)`` in ``dtype`` (float32 or int16)."""
    x = planar.T
    if np.dtype(dtype) == np.int16:
        return np.clip(np.round(x * 32768.0), -32768, 32767).astype(np.int16)
    if np.dtype(dtype) == np.float32:
        return np.ascontiguousarray(x, dtype=np.float32)
    raise AudioFormatError(f"unsupported output dtype {dtype}")


def downmix_mono(planar: Float32Array) -> Float32Array:
    """Average channels into a ``(1, samples)`` array."""
    if planar.shape[0] == 1:
        return planar
    mixed: Float32Array = np.asarray(planar.mean(axis=0, keepdims=True), dtype=np.float32)
    return mixed


def rms_dbfs(planar: Float32Array) -> float:
    """RMS level in dBFS (full-scale sine = -3 dBFS). Returns -inf for silence."""
    if planar.size == 0:
        return float("-inf")
    rms = float(np.sqrt(np.mean(np.square(planar, dtype=np.float64))))
    return 20.0 * np.log10(rms) if rms > 0 else float("-inf")
