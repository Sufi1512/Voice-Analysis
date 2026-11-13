"""Quality metrics. All functions take signals already aligned (latency removed)."""

from __future__ import annotations

import re

import numpy as np
from scipy.signal import correlate

EPS = 1e-12
FRAME_S = 0.02


def db(power: float) -> float:
    return float(10 * np.log10(max(power, EPS)))


def frames(x: np.ndarray, rate: int, frame_s: float = FRAME_S) -> np.ndarray:
    hop = int(rate * frame_s)
    m = len(x) // hop
    return np.mean(x[: m * hop].astype(np.float64).reshape(m, hop) ** 2, axis=1)


def align(out: np.ndarray, delay: int, n: int) -> np.ndarray:
    """Drop the pipeline delay and trim/pad to ``n`` samples."""
    y = out[delay : delay + n]
    return np.pad(y, (0, n - len(y))) if len(y) < n else y


def estimate_delay(ref: np.ndarray, out: np.ndarray, max_lag: int) -> int:
    c = correlate(out[: len(ref) + max_lag], ref, mode="full", method="fft")
    mid = len(ref) - 1
    return int(np.argmax(c[mid : mid + max_lag + 1]))


def si_sdr(ref: np.ndarray, est: np.ndarray) -> float:
    r = ref.astype(np.float64)
    e = est.astype(np.float64)
    a = np.dot(e, r) / (np.dot(r, r) + EPS)
    t = a * r
    return db(float(np.sum(t**2)) / (float(np.sum((e - t) ** 2)) + EPS))


def stoi(ref: np.ndarray, est: np.ndarray, rate: int) -> float:
    from pystoi import stoi as _stoi

    return float(_stoi(ref.astype(np.float64), est.astype(np.float64), rate, extended=False))


def speech_mask(
    clean: np.ndarray, noise: np.ndarray | None, rate: int, floor_db: float = 35.0
) -> np.ndarray:
    """20 ms frames where speech is clearly present and louder than the noise in that frame."""
    c = frames(clean, rate)
    mask = c > c.max() * 10 ** (-floor_db / 10)
    if noise is not None and np.any(noise):
        mask &= c > frames(noise, rate)
    return mask


def speech_cut_pct(
    clean: np.ndarray, noise: np.ndarray | None, out: np.ndarray, rate: int
) -> float:
    """Audible speech removed: % of speech frames where the output is >10 dB below clean."""
    mask = speech_mask(clean, noise, rate)
    if not mask.any():
        return 0.0
    c = frames(clean, rate)[mask]
    o = frames(out, rate)[: len(mask)][mask]
    return float(100 * np.mean(o < c * 0.1))


def region(n: int, rate: int, spans: list[tuple[float, float]]) -> np.ndarray:
    m = np.zeros(n, bool)
    for s, e in spans:
        m[max(0, int(s * rate)) : min(n, int(e * rate))] = True
    return m


def pause_spans(n: int, rate: int, speech: tuple[float, float]) -> list[tuple[float, float]]:
    """Noise-only parts: after 0.5 s of convergence until 0.1 s before speech, and the tail."""
    s, e = speech
    return [(0.5, s - 0.1), (e + 0.4, n / rate - 0.1)]


def pause_noise_db(
    noise: np.ndarray, out: np.ndarray, rate: int, speech: tuple[float, float]
) -> float:
    """Output level in pauses relative to the input noise there (negative = removed)."""
    m = region(len(noise), rate, pause_spans(len(noise), rate, speech))
    return db(float(np.mean(out[m].astype(np.float64) ** 2))) - db(
        float(np.mean(noise[m].astype(np.float64) ** 2))
    )


def pause_level_dbfs(out: np.ndarray, rate: int, speech: tuple[float, float]) -> float:
    """Absolute output level in pauses (dBFS): what a listener actually hears there."""
    m = region(len(out), rate, pause_spans(len(out), rate, speech))
    return db(float(np.mean(out[m].astype(np.float64) ** 2)))


def pumping_db(
    out: np.ndarray, rate: int, speech: tuple[float, float], silent_dbfs: float = -70.0
) -> float:
    """Spread (std, dB) of 50 ms output levels in pauses. Below -70 dBFS counts as silence."""
    m = region(len(out), rate, pause_spans(len(out), rate, speech))
    lv = 10 * np.log10(frames(np.where(m, out, 0.0), rate, 0.05) + EPS)
    keep = frames(m.astype(np.float64), rate, 0.05) > 0.99
    if keep.sum() < 4:
        return 0.0
    return float(np.std(np.maximum(lv[keep], silent_dbfs)))


def under_voice_db(clean: np.ndarray, noise: np.ndarray, out: np.ndarray, rate: int) -> float:
    """Noise left under the voice: residual (output minus scaled speech) vs input noise."""
    mask = speech_mask(clean, None, rate)
    hop = int(rate * FRAME_S)
    idx = np.repeat(mask, hop)
    n = min(len(idx), len(clean))
    c, o, z = clean[:n][idx[:n]], out[:n][idx[:n]], noise[:n][idx[:n]]
    a = np.dot(o, c) / (np.dot(c, c) + EPS)
    res = o - a * c
    return db(float(np.mean(res**2))) - db(float(np.mean(z.astype(np.float64) ** 2)))


def erle_db(mic: np.ndarray, out: np.ndarray, mask: np.ndarray) -> float:
    """Echo return loss enhancement over far-end-only samples."""
    return db(float(np.mean(mic[mask].astype(np.float64) ** 2))) - db(
        float(np.mean(out[mask].astype(np.float64) ** 2))
    )


_PUNCT = re.compile(r"[^a-z0-9' ]+")


def normalize_text(text: str) -> list[str]:
    return _PUNCT.sub(" ", text.lower()).split()


def word_errors(ref: str, hyp: str) -> tuple[int, int]:
    """(edit distance in words, reference word count)."""
    r, h = normalize_text(ref), normalize_text(hyp)
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            cur = d[j]
            d[j] = min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
            prev = cur
    return d[len(h)], len(r)
