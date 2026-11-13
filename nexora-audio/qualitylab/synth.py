"""Seeded signal generators: synthetic noise, rooms, echo paths, phone lines and loss."""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, fftconvolve, resample_poly, sosfilt

from nexora_audio.streaming.codecs import AudioFormat, StreamDecoder, encode

F32 = np.float32


def _rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


def _unit(x: np.ndarray) -> np.ndarray:
    return (x / (np.sqrt(np.mean(x.astype(np.float64) ** 2)) + 1e-12)).astype(F32)


def white(n: int, seed: int) -> np.ndarray:
    return _unit(_rng(seed).standard_normal(n))


def colored(n: int, seed: int, exponent: float) -> np.ndarray:
    """1/f^exponent noise: 1 = pink, 2 = brown."""
    spec = np.fft.rfft(_rng(seed).standard_normal(n))
    f = np.arange(len(spec), dtype=np.float64)
    f[0] = 1.0
    return _unit(np.fft.irfft(spec / f ** (exponent / 2), n))


def hum(n: int, rate: int, seed: int, mains: float = 60.0) -> np.ndarray:
    """Mains hum with harmonics and slight level drift (60 Hz in Saudi Arabia)."""
    t = np.arange(n) / rate
    rng = _rng(seed)
    x = sum(
        (0.6**k) * np.sin(2 * np.pi * mains * (k + 1) * t + rng.uniform(0, 2 * np.pi))
        for k in range(5)
    )
    x = x * (1 + 0.1 * np.sin(2 * np.pi * 0.3 * t)) + 0.05 * rng.standard_normal(n)
    return _unit(x)


def keyboard(n: int, rate: int, seed: int) -> np.ndarray:
    rng = _rng(seed)
    out = np.zeros(n, F32)
    click = int(0.015 * rate)
    env = np.exp(-np.arange(click) / (0.002 * rate))
    t = 0
    while True:
        t += int(rng.uniform(0.08, 0.25) * rate)
        if t + click >= n:
            break
        out[t : t + click] += (env * rng.standard_normal(click)).astype(F32)
    return _unit(out)


def music(n: int, rate: int, seed: int) -> np.ndarray:
    """Instrumental stand-in: chord progression with plucked envelopes and a kick drum."""
    rng = _rng(seed)
    t = np.arange(n) / rate
    out = np.zeros(n)
    beat = 0.5
    roots = [220.0, 174.6, 196.0, 261.6]
    for i in range(int(n / rate / beat)):
        s = int(i * beat * rate)
        e = min(n, s + int(beat * rate))
        tt = t[s:e] - t[s]
        root = roots[(i // 4) % 4]
        env = np.exp(-tt * 4)
        for ratio in (1.0, 1.26, 1.5, 2.0):
            out[s:e] += env * np.sin(2 * np.pi * root * ratio * tt + rng.uniform(0, 6.28))
        out[s:e] += 2.0 * np.exp(-tt * 30) * np.sin(2 * np.pi * 55 * tt)
    return _unit(out)


SYNTH_NOISES = ("white", "pink", "brown", "hum", "keyboard", "music")


def synth_noise(name: str, n: int, rate: int, seed: int) -> np.ndarray:
    if name == "white":
        return white(n, seed)
    if name == "pink":
        return colored(n, seed, 1.0)
    if name == "brown":
        return colored(n, seed, 2.0)
    if name == "hum":
        return hum(n, rate, seed)
    if name == "keyboard":
        return keyboard(n, rate, seed)
    if name == "music":
        return music(n, rate, seed)
    raise ValueError(name)


def fit(noise: np.ndarray, n: int, seed: int) -> np.ndarray:
    """Cut ``n`` samples from a noise recording at a seeded offset, looping if short."""
    if len(noise) < n:
        noise = np.tile(noise, n // len(noise) + 2)
    start = int(_rng(seed).integers(0, len(noise) - n + 1))
    return _unit(noise[start : start + n])


def scale_to_snr(speech: np.ndarray, noise: np.ndarray, snr_db: float) -> np.ndarray:
    """Noise scaled so active speech is ``snr_db`` above it (speech power over voiced frames)."""
    p_speech = active_power(speech)
    p_noise = float(np.mean(noise.astype(np.float64) ** 2)) + 1e-20
    return (noise * np.sqrt(p_speech / (p_noise * 10 ** (snr_db / 10)))).astype(F32)


def active_power(x: np.ndarray, rate: int = 16000, floor_db: float = 35.0) -> float:
    """Mean power of 20 ms frames within ``floor_db`` of the loudest frame."""
    hop = int(0.02 * rate)
    m = len(x) // hop
    e = np.mean(x[: m * hop].astype(np.float64).reshape(m, hop) ** 2, axis=1)
    keep = e > e.max() * 10 ** (-floor_db / 10)
    return float(e[keep].mean())


def room_ir(rate: int, rt60: float, seed: int) -> np.ndarray:
    """Exponentially decaying noise tail with a direct path: a simple synthetic room."""
    n = int(rt60 * rate)
    rng = _rng(seed)
    tail = rng.standard_normal(n) * np.exp(-6.9 * np.arange(n) / n)
    tail[: int(0.003 * rate)] = 0
    ir = 0.35 * tail / np.sqrt(np.sum(tail**2))
    ir[0] = 1.0
    return ir.astype(F32)


def reverb(x: np.ndarray, ir: np.ndarray) -> np.ndarray:
    return fftconvolve(x, ir)[: len(x)].astype(F32)


def echo_path(
    ref: np.ndarray, rate: int, delay_ms: float, seed: int, drive: float = 2.0
) -> np.ndarray:
    """What a speakerphone sends back: delayed, band-limited, distorted, reverberant agent audio."""
    sos = butter(4, [200, min(4000, rate / 2 - 100)], btype="band", fs=rate, output="sos")
    y = sosfilt(sos, ref)
    y = np.tanh(drive * y / (np.max(np.abs(y)) + 1e-9)) / np.tanh(drive)  # small-speaker overdrive
    y = fftconvolve(y, room_ir(rate, 0.25, seed))[: len(ref)]
    d = int(delay_ms * rate / 1000)
    return np.concatenate([np.zeros(d), y[: len(ref) - d]]).astype(F32)


def phone_line(x: np.ndarray, encoding: str = "mulaw") -> tuple[np.ndarray, bytes]:
    """16 kHz audio -> 300-3400 Hz band -> 8 kHz -> G.711. Returns (decoded 8 kHz, wire bytes)."""
    y = resample_poly(x, 1, 2)
    sos = butter(6, [300, 3400], btype="band", fs=8000, output="sos")
    y = np.clip(sosfilt(sos, y), -1, 1).astype(F32)
    fmt = AudioFormat(encoding=encoding, sample_rate=8000)  # type: ignore[arg-type]
    wire = encode(y[None, :], fmt)
    return StreamDecoder(fmt).decode(wire)[0].astype(F32), wire


def band8k(x16: np.ndarray) -> np.ndarray:
    """Same band-limiting as the phone line, without the codec (clean phone reference)."""
    y = resample_poly(x16, 1, 2)
    sos = butter(6, [300, 3400], btype="band", fs=8000, output="sos")
    return sosfilt(sos, y).astype(F32)


def gilbert_loss(n_packets: int, rate_pct: float, seed: int, burst: float = 2.0) -> np.ndarray:
    """Packet-loss mask (True = lost) from a two-state Gilbert model with mean burst length."""
    if rate_pct <= 0:
        return np.zeros(n_packets, bool)
    p_bad_to_good = 1.0 / burst
    loss = rate_pct / 100.0
    p_good_to_bad = loss * p_bad_to_good / (1 - loss)
    rng = _rng(seed)
    lost = np.zeros(n_packets, bool)
    bad = False
    for i in range(n_packets):
        bad = rng.random() < (1 - p_bad_to_good if bad else p_good_to_bad)
        lost[i] = bad
    return lost


def apply_loss(x: np.ndarray, rate: int, mask: np.ndarray, packet_ms: float = 20.0) -> np.ndarray:
    """Zero the lost packets: what reaches us today, with no concealment."""
    hop = int(rate * packet_ms / 1000)
    y = x.copy()
    for i in np.flatnonzero(mask):
        y[i * hop : (i + 1) * hop] = 0
    return y
