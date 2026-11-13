"""The quality lab's own metrics, generators and gate logic must be right before we trust them."""

import numpy as np
import pytest
from qualitylab import gates, metrics, synth

RATE = 16000


def _speechlike(seconds: float = 3.0, seed: int = 0) -> np.ndarray:
    t = np.arange(int(seconds * RATE)) / RATE
    env = (np.sin(2 * np.pi * 2.5 * t) > 0).astype(np.float32)  # syllable bursts
    rng = np.random.default_rng(seed)
    voiced = sum(np.sin(2 * np.pi * f * t) for f in (180, 360, 540, 900))
    return (0.1 * env * (voiced + 0.3 * rng.standard_normal(len(t)))).astype(np.float32)


def test_speech_cut_detects_removed_speech() -> None:
    x = _speechlike()
    assert metrics.speech_cut_pct(x, None, x, RATE) == 0.0
    y = x.copy()
    y[: len(y) // 2] *= 0.01  # -40 dB on the first half
    assert 40 < metrics.speech_cut_pct(x, None, y, RATE) < 60
    assert metrics.speech_cut_pct(x, None, x * 0.5, RATE) == 0.0  # -6 dB is not a cut


def test_si_sdr_and_alignment() -> None:
    x = _speechlike()
    noisy = x + 0.01 * synth.white(len(x), 3)
    assert metrics.si_sdr(x, 2 * x) > 100
    assert 15 < metrics.si_sdr(x, noisy) < 30
    delayed = np.concatenate([np.zeros(512, np.float32), x])
    assert metrics.estimate_delay(x, delayed, 2000) == 512
    assert np.array_equal(metrics.align(delayed, 512, len(x)), x)


def test_pause_noise_and_pumping() -> None:
    n = 6 * RATE
    noise = 0.01 * synth.white(n, 1)
    span = (2.0, 4.0)
    assert metrics.pause_noise_db(noise, noise * 0.1, RATE, span) == pytest.approx(-20, abs=0.1)
    assert metrics.pumping_db(noise, RATE, span) < 1.0
    gated = noise.copy()
    blocks = gated.reshape(-1, RATE // 10)
    blocks[::2] *= 0.03  # on/off every 100 ms
    assert metrics.pumping_db(blocks.ravel(), RATE, span) > 10


def test_word_errors() -> None:
    assert metrics.word_errors("Ask not, what your country", "ask not what your country") == (0, 5)
    assert metrics.word_errors("a b c d", "a x c") == (2, 4)


def test_snr_scaling_and_loss_model() -> None:
    x = _speechlike()
    nz = synth.scale_to_snr(x, synth.white(len(x), 2), 10)
    p_speech = synth.active_power(x)
    assert 10 * np.log10(p_speech / np.mean(nz.astype(np.float64) ** 2)) == pytest.approx(10, 0.01)
    mask = synth.gilbert_loss(20000, 5, seed=1)
    assert 4.0 < 100 * mask.mean() < 6.0
    assert not synth.gilbert_loss(100, 0, seed=1).any()


def test_phone_line_roundtrip_is_8k_band_limited() -> None:
    x = _speechlike()
    y, wire = synth.phone_line(x)
    assert len(wire) == len(y) == len(x) // 2
    spec = np.abs(np.fft.rfft(y))
    f = np.fft.rfftfreq(len(y), 1 / 8000)
    assert spec[f < 150].sum() < 0.05 * spec[(f > 300) & (f < 3400)].sum()


def test_gate_evaluation_and_regression() -> None:
    rows = [
        {"id": "a", "set": "noise", "snr": 0, "speech_cut_pct": 1.0},
        {"id": "b", "set": "noise", "snr": -5, "speech_cut_pct": 9.0},  # below min_snr
        {"id": "c", "set": "noise", "snr": 10, "speech_cut_pct": 1.5},
    ]
    g = [
        {
            "id": "cut",
            "title": "t",
            "metric": "speech_cut_pct",
            "sets": ["noise"],
            "min_snr": 0,
            "agg": "max",
            "op": "<=",
            "threshold": 2.0,
            "tolerance": 0.2,
            "enforce": True,
        }
    ]
    (res,) = gates.evaluate(rows, None, g)
    assert res.value == 1.5 and res.passed and not gates.failed([res])
    (res,) = gates.evaluate(rows, {"cut": 1.0}, g)
    assert res.regressed and gates.failed([res])  # 1.5 is worse than 1.0 + 0.2
    rows[2]["speech_cut_pct"] = 3.0
    (res,) = gates.evaluate(rows, None, g)
    assert res.passed is False and gates.failed([res])


def test_wer_pooling() -> None:
    rows = [
        {"id": "a", "set": "noise", "snr": 0, "words": 10, "errors_in": 4, "errors_out": 2},
        {"id": "b", "set": "noise", "snr": 0, "words": 30, "errors_in": 0, "errors_out": 0},
    ]
    g = {
        "id": "w",
        "title": "t",
        "metric": "wer",
        "sets": ["noise"],
        "agg": "wer_reduction",
        "op": ">=",
        "threshold": 20,
    }
    (res,) = gates.evaluate(rows, None, [g])
    assert res.value == pytest.approx(50.0)
