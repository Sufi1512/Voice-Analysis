"""RNNoise backend on real speech. Thresholds sit well below measured values
(see docs/PHASE1_TECHNICAL_PLAN.md) so they catch regressions, not noise."""

import numpy as np
import pytest
from scipy.signal import correlate

from nexora_audio import BackendError, NexoraAudio
from nexora_audio.backends import rnnoise
from nexora_audio.backends.rnnoise import LATENCY_SAMPLES, RNNoiseProcessor
from tests.audio_fixtures import keyboard, mix, pink, si_sdr, speech, white


def run_processor(proc: RNNoiseProcessor, x: np.ndarray) -> np.ndarray:
    n = len(x) // 480 * 480
    frames = x[:n].reshape(-1, 480)
    return np.concatenate([proc.process(f[None, :])[0] for f in frames])


def test_bundled_library_loads() -> None:
    assert rnnoise.probe() is None
    caps = NexoraAudio().capabilities()["noise_cancellation"]
    assert caps.available and caps.backend == "rnnoise"


def test_env_var_is_tried_first(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(rnnoise.ENV_VAR, "/nonexistent/librnnoise.so")
    assert rnnoise.candidate_paths()[0] == "/nonexistent/librnnoise.so"


def test_measured_delay_matches_declared_latency() -> None:
    x = speech(48000)
    y = run_processor(RNNoiseProcessor(), x)
    lag = int(np.argmax(correlate(y, x[: len(y)], "full"))) - (len(y) - 1)
    assert lag == LATENCY_SAMPLES


@pytest.mark.parametrize(
    "noise,snr_in,min_gain",
    [("white", 0, 8.0), ("white", 5, 6.0), ("pink", 5, 3.0), ("keyboard", 5, 3.0)],
)
def test_improves_noisy_speech(noise: str, snr_in: float, min_gain: float) -> None:
    clean = speech(48000)
    n = {"white": white, "pink": pink}.get(noise)
    noise_sig = n(len(clean)) if n else keyboard(len(clean), 48000)
    noisy = mix(clean, noise_sig, snr_in)
    y = run_processor(RNNoiseProcessor(), noisy)[LATENCY_SAMPLES:]
    ref = clean[: len(y)]
    before, after = si_sdr(ref, noisy[: len(y)]), si_sdr(ref, y)
    assert after - before > min_gain, f"{noise}@{snr_in}dB: {before:.1f} -> {after:.1f} dB"


def test_silence_stays_silent() -> None:
    y = run_processor(RNNoiseProcessor(), np.zeros(48000, np.float32))
    assert np.max(np.abs(y)) < 1e-4


def test_strength_zero_is_delayed_original() -> None:
    x = speech(48000)[:48000]
    y = run_processor(RNNoiseProcessor(strength=0.0), x)
    np.testing.assert_allclose(y[LATENCY_SAMPLES:], x[: len(y) - LATENCY_SAMPLES], atol=1e-6)


def test_partial_strength_sits_between() -> None:
    clean = speech(48000)
    noisy = mix(clean, white(len(clean)), 0)

    def score(s: float) -> float:
        y = run_processor(RNNoiseProcessor(strength=s), noisy)[LATENCY_SAMPLES:]
        return si_sdr(clean[: len(y)], y)

    assert score(0.0) < score(0.5) < score(1.0)


def test_stereo_channels_are_independent() -> None:
    x = speech(48000)[:48000]
    proc = RNNoiseProcessor(channels=2)
    st = np.stack([x, np.zeros_like(x)])
    out = np.concatenate([proc.process(st[:, i : i + 480]) for i in range(0, 48000, 480)], axis=1)
    mono = run_processor(RNNoiseProcessor(), x)
    np.testing.assert_allclose(out[0], mono, atol=1e-6)
    assert np.max(np.abs(out[1])) < 1e-4


def test_reset_restarts_stream_and_close_is_final() -> None:
    x = mix(speech(48000), white(len(speech(48000))), 5)[:24000]
    proc = RNNoiseProcessor()
    a = run_processor(proc, x)
    proc.reset()
    np.testing.assert_array_equal(run_processor(proc, x), a)
    proc.close()
    with pytest.raises(BackendError, match="closed"):
        proc.process(np.zeros((1, 480), np.float32))


def test_rejects_bad_arguments() -> None:
    with pytest.raises(BackendError):
        RNNoiseProcessor(channels=3)
    with pytest.raises(BackendError):
        RNNoiseProcessor(strength=1.5)
