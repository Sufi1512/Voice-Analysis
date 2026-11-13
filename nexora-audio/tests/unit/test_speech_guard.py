"""Speech guard: restores speech a model removed, never restores noise."""

import numpy as np

from nexora_audio.core.speech_guard import SpeechGuard

N, FS = 480, 48000


def _run(g: SpeechGuard, x: np.ndarray, model, prob) -> np.ndarray:
    out = []
    for i in range(0, len(x) // N * N, N):
        k = i // N
        out.append(g.process(x[i : i + N], model(k), prob(k)))
    return np.concatenate(out)


def _bursts(seconds: float, level: float, noise: float, seed: int = 0) -> np.ndarray:
    """Speech-like: 250 ms tones every 500 ms over a steady noise floor."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * FS)) / FS
    on = (t % 0.5) < 0.25
    return (level * on * np.sin(2 * np.pi * 300 * t) + noise * rng.standard_normal(len(t))).astype(
        np.float32
    )


def test_restores_speech_the_model_removed() -> None:
    x = _bursts(4.0, 0.1, 0.001)
    g = SpeechGuard(N, N / FS, latency=1440, margin_db=6.0)
    y = _run(g, x, lambda k: np.zeros(N, np.float32), lambda k: 1.0)
    aligned = x[: len(y) - 1440]
    late = slice(FS, len(aligned))
    e_in = np.mean(aligned[late] ** 2)
    e_out = np.mean(y[1440:][late] ** 2)
    assert 10 * np.log10(e_in / e_out) < 7.5  # at most the 6 dB margin (+ ramp slack)
    assert g.restored_frames > 0


def test_noise_at_the_floor_is_never_restored() -> None:
    rng = np.random.default_rng(1)
    x = (0.01 * rng.standard_normal(5 * FS)).astype(np.float32)
    g = SpeechGuard(N, N / FS, latency=1440)
    y = _run(g, x, lambda k: np.zeros(N, np.float32), lambda k: 1.0)
    assert np.mean(y[FS:] ** 2) < 1e-3 * np.mean(x**2)


def test_low_speech_probability_is_not_protected() -> None:
    x = _bursts(3.0, 0.1, 0.001)
    g = SpeechGuard(N, N / FS, latency=1440, min_probability=0.35)
    y = _run(g, x, lambda k: np.zeros(N, np.float32), lambda k: 0.2)
    assert not y.any()


def test_floor_catches_up_when_noise_starts_after_silence() -> None:
    rng = np.random.default_rng(2)
    quiet = np.zeros(2 * FS, np.float32)
    noise = (0.02 * rng.standard_normal(8 * FS)).astype(np.float32)
    x = np.concatenate([quiet, noise])
    g = SpeechGuard(N, N / FS, latency=1440)
    y = _run(g, x, lambda k: np.zeros(N, np.float32), lambda k: 1.0)
    tail = y[7 * FS :]  # 5 s after the noise started: floor has caught up
    assert np.mean(tail**2) < 1e-3 * np.mean(noise**2)
