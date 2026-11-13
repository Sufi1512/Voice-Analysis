"""Speech-to-text for the transcription-accuracy gate (Whisper tiny.en via sherpa-onnx).

Whisper tiny.en is a small stand-in for the customer's STT. Its job here is relative:
does processing make transcription better or worse than the raw input? The reference
transcript is the same model's output on the clean speech, so the WER measures damage
from noise and processing, not the model's own mistakes.
"""

from __future__ import annotations

import os
from functools import cache
from typing import Any

import numpy as np
from scipy.signal import resample_poly

from qualitylab import sources

# Use the model files exactly as published, so local runs and CI match.
os.environ.setdefault("SANDBOX_SHERPA_ONNX_WHISPER_FILES", "0")


@cache
def _recognizer() -> Any:
    import sherpa_onnx

    d = sources.stt_dir()
    if d is None:
        raise RuntimeError("STT model missing: run `python -m qualitylab fetch --stt`")
    return sherpa_onnx.OfflineRecognizer.from_whisper(
        encoder=str(d / "tiny.en-encoder.int8.onnx"),
        decoder=str(d / "tiny.en-decoder.int8.onnx"),
        tokens=str(d / "tiny.en-tokens.txt"),
        language="en",
        task="transcribe",
        num_threads=1,
    )


def available() -> bool:
    try:
        import sherpa_onnx  # noqa: F401
    except ImportError:
        return False
    return sources.stt_dir() is not None


def transcribe(x: np.ndarray, rate: int) -> str:
    if rate != 16000:
        x = resample_poly(x, 16000, rate).astype(np.float32)
    rec = _recognizer()
    s = rec.create_stream()
    s.accept_waveform(16000, np.clip(x, -1, 1).astype(np.float32))
    rec.decode_stream(s)
    return str(s.result.text).strip()
