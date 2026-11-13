"""WebRTC AEC3 echo canceller (bundled libnexora_aec)."""

import numpy as np
import pytest

from nexora_audio.backends import aec3

pytestmark = pytest.mark.skipif(aec3.probe() is not None, reason="libnexora_aec not available")

RATE = 16000


def talk(seconds: float, seed: int, f0: float) -> np.ndarray:
    """Speech-like: harmonic bursts with syllable gaps."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * RATE)) / RATE
    env = np.repeat(rng.random(int(seconds * 5) + 1) > 0.3, RATE // 5)[: len(t)]
    voiced = sum(np.sin(2 * np.pi * f0 * k * t + rng.uniform(0, 6)) / k for k in range(1, 6))
    return (0.05 * env * voiced).astype(np.float32)


def run(p: aec3.AEC3Processor, mic: np.ndarray, ref: np.ndarray) -> np.ndarray:
    n = p.native_frame_size
    out = []
    for i in range(0, len(mic) - n + 1, n):
        p.push_reference(ref[i : i + n])
        out.append(p.process(mic[None, i : i + n])[0])
    return np.concatenate(out)


def db(x: np.ndarray) -> float:
    return float(10 * np.log10(np.mean(x.astype(np.float64) ** 2) + 1e-12))


def test_removes_speakerphone_echo() -> None:
    ref = talk(8.0, 1, 140)
    d = int(0.12 * RATE)
    echo = 0.5 * np.convolve(ref, np.exp(-np.arange(800) / 150) / 20)[: len(ref)]
    mic = np.concatenate([np.zeros(d, np.float32), echo[:-d]]).astype(np.float32)
    y = run(aec3.AEC3Processor(RATE), mic, ref)
    late = slice(3 * RATE, len(y))
    # near-transparent tuning trades some echo removal for keeping the caller (lab median 27 dB)
    assert db(mic[late]) - db(y[late]) > 12


def test_headset_caller_passes_through() -> None:
    ref = talk(6.0, 2, 140)
    caller = np.zeros_like(ref)
    caller[3 * RATE :] = talk(3.0, 3, 210)
    p = aec3.AEC3Processor(RATE)
    y = run(p, caller, ref)
    late = slice(int(3.5 * RATE), len(y))
    assert abs(db(caller[late]) - db(y[late])) < 1.0  # no echo path: caller untouched
    assert p.guarded_frames > 0


def test_reset_and_stats() -> None:
    p = aec3.AEC3Processor(RATE)
    run(p, talk(1.0, 4, 140), talk(1.0, 5, 140))
    s = p.stats()
    assert set(s) == {"erle_db", "erl_db", "delay_ms", "residual_echo_likelihood"}
    p.reset()
    assert p.native_frame_size == 160
    p.close()


def test_rejects_unsupported_rate() -> None:
    from nexora_audio.exceptions import BackendError

    with pytest.raises(BackendError):
        aec3.AEC3Processor(22050)
