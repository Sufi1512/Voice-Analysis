"""Learned end-of-turn detection with Smart Turn v3.2 (Daily / Pipecat, BSD-2-Clause).

Smart Turn listens to the last 8 seconds of the caller's turn and judges whether it
sounds finished: from intonation, rhythm and the shape of the last words, not just from
silence. "I'd like to book a flight to..." followed by a pause sounds unfinished; "Yes,
that's all." sounds finished.

The model (``_models/smart-turn-v3.2-cpu.onnx``, int8, 8.7 MB) comes unchanged from the
``pipecat-ai`` 1.16.0 wheel; code, weights and training data are BSD-2-Clause. Features are
Whisper-style log-mel spectrograms (``_whisper_features.py``, vendored from the same
wheel). See ``THIRD_PARTY_NOTICES.md``.
"""

from __future__ import annotations

import threading
from functools import cache
from pathlib import Path
from typing import Any

import numpy as np

from nexora_audio.backends._whisper_features import compute_whisper_log_mel_features
from nexora_audio.exceptions import BackendError
from nexora_audio.utils.audio_utils import Float32Array

MODEL_RATE = 16000
WINDOW_S = 8
_MODEL = Path(__file__).resolve().parent.parent / "_models" / "smart-turn-v3.2-cpu.onnx"
_lock = threading.Lock()


def model_path() -> Path:
    return _MODEL


def probe() -> str | None:
    if not _MODEL.exists():
        return f"Smart Turn model missing: {_MODEL}"
    try:
        import onnxruntime  # noqa: F401
    except ImportError:
        return "onnxruntime is not installed"
    return None


@cache
def _session() -> Any:
    import onnxruntime as ort

    so = ort.SessionOptions()
    so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    so.inter_op_num_threads = 1
    so.intra_op_num_threads = 1
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    try:
        return ort.InferenceSession(str(_MODEL), sess_options=so)
    except Exception as exc:  # pragma: no cover - corrupted install
        raise BackendError(f"cannot load Smart Turn model: {exc}") from exc


def complete_probability(audio: Float32Array) -> float:
    """Probability (0-1) that the turn in ``audio`` (16 kHz mono, its end = now) is finished."""
    x = np.asarray(audio, dtype=np.float32)
    n = WINDOW_S * MODEL_RATE
    x = x[-n:] if len(x) > n else np.pad(x, (n - len(x), 0))
    feats = compute_whisper_log_mel_features(x, do_normalize=True)
    with _lock:  # one shared session; inference is short
        out = _session().run(None, {"input_features": feats[None, ...].astype(np.float32)})
    return float(np.asarray(out[0]).reshape(-1)[0])
