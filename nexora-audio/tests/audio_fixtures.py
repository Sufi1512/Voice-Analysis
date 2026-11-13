"""Real speech fixture plus seeded noise generators for quality tests."""

from __future__ import annotations

from functools import cache
from pathlib import Path

import numpy as np
from scipy.signal import resample_poly

FIXTURES = Path(__file__).parent / "fixtures"
SPEECH_16K = FIXTURES / "jfk_inaugural_16k.wav"


@cache
def speech(rate: int = 48000) -> np.ndarray:
    """JFK inaugural excerpt (public domain) as float32 mono at ``rate``."""
    import soundfile as sf

    x, sr = sf.read(str(SPEECH_16K), dtype="float32")
    assert sr == 16000
    if rate != 16000:
        g = np.gcd(rate, 16000)
        x = resample_poly(x, rate // g, 16000 // g).astype(np.float32)
    return x


def white(n: int, seed: int = 0) -> np.ndarray:
    return np.random.default_rng(seed).standard_normal(n).astype(np.float32)


def pink(n: int, seed: int = 1) -> np.ndarray:
    spec = np.fft.rfft(np.random.default_rng(seed).standard_normal(n))
    f = np.arange(len(spec), dtype=np.float64)
    f[0] = 1.0
    x = np.fft.irfft(spec / np.sqrt(f), n)
    return (x / x.std()).astype(np.float32)


def keyboard(n: int, rate: int, seed: int = 2) -> np.ndarray:
    """Sharp decaying clicks at random intervals (a rough typing stand-in)."""
    rng = np.random.default_rng(seed)
    out = np.zeros(n, np.float32)
    click_len = int(0.015 * rate)
    env = np.exp(-np.arange(click_len) / (0.002 * rate)).astype(np.float32)
    t = 0
    while True:
        t += int(rng.uniform(0.08, 0.25) * rate)
        if t + click_len >= n:
            break
        out[t : t + click_len] += env * rng.standard_normal(click_len).astype(np.float32)
    return out / (out.std() + 1e-9)


def mix(clean: np.ndarray, noise: np.ndarray, snr_db: float) -> np.ndarray:
    scale = np.sqrt(np.mean(clean**2) / (np.mean(noise**2) * 10 ** (snr_db / 10)))
    return (clean + scale * noise).astype(np.float32)


def si_sdr(ref: np.ndarray, est: np.ndarray) -> float:
    """Scale-invariant signal-to-distortion ratio in dB."""
    ref = ref.astype(np.float64)
    est = est.astype(np.float64)
    alpha = np.dot(est, ref) / np.dot(ref, ref)
    target = alpha * ref
    return float(10 * np.log10(np.sum(target**2) / np.sum((est - target) ** 2)))
