"""DeepFilterNet3 backend on real speech: delay, quality, speech gating, pause gate."""

import numpy as np
import pytest
from scipy.signal import correlate

from nexora_audio import BackendError, NexoraAudio
from nexora_audio.backends import deepfilternet as dfn
from nexora_audio.backends.deepfilternet import LATENCY_SAMPLES, DeepFilterNetProcessor
from tests.audio_fixtures import mix, pink, si_sdr, speech, white

pytestmark = pytest.mark.skipif(
    dfn.probe() is not None, reason=f"DeepFilterNet not available here: {dfn.probe()}"
)


def run(proc: DeepFilterNetProcessor, x: np.ndarray) -> np.ndarray:
    n = len(x) // 480 * 480
    return np.concatenate([proc.process(x[None, i : i + 480])[0] for i in range(0, n, 480)])


def padded(rate: int = 48000) -> np.ndarray:
    z = np.zeros(2 * rate, np.float32)
    return np.concatenate([z, speech(rate), z])


def frame_db(x: np.ndarray, f: int = 480) -> np.ndarray:
    k = len(x) // f
    return 10 * np.log10(np.mean(x[: k * f].reshape(k, f) ** 2, axis=1) + 1e-20)


def test_available_and_preferred() -> None:
    assert dfn.probe() is None
    assert NexoraAudio().capabilities()["noise_cancellation"].backend == "deepfilternet3"


def test_measured_delay_matches_declared_latency() -> None:
    x = speech(48000)
    y = run(DeepFilterNetProcessor(), x)
    lag = int(np.argmax(correlate(y, x[: len(y)], "full"))) - (len(y) - 1)
    assert lag == LATENCY_SAMPLES


def test_improves_noisy_speech() -> None:
    clean = speech(48000)
    noisy = mix(clean, white(len(clean)), 0)
    y = run(DeepFilterNetProcessor(), noisy)[LATENCY_SAMPLES:]
    ref = clean[: len(y)]
    assert si_sdr(ref, y) - si_sdr(ref, noisy[: len(y)]) > 8.0


def test_pause_gate_cleans_bursty_low_frequency_noise() -> None:
    """Ungated DFN3 lets pink-noise bursts through in pauses; the gate removes them."""
    clean = padded()
    noise = pink(len(clean))
    noisy = mix(clean, noise, 10)
    noise = noisy - clean
    pause = slice(int(0.6 * 48000) + LATENCY_SAMPLES, 2 * 48000)

    def pause_db(proc: DeepFilterNetProcessor) -> float:
        y = run(proc, noisy)[LATENCY_SAMPLES:]
        return float(10 * np.log10(np.mean(y[pause] ** 2) / np.mean(noise[pause] ** 2)))

    ungated = pause_db(DeepFilterNetProcessor())
    gated = pause_db(DeepFilterNetProcessor(speech_atten_lim_db=20, pause_gate_db=40))
    assert gated < -35.0
    assert gated < ungated - 10.0


def test_gating_does_not_cut_audible_speech() -> None:
    clean = padded()
    noisy = mix(clean, white(len(clean)), 5)
    noise = noisy - clean
    y = run(DeepFilterNetProcessor(speech_atten_lim_db=20, pause_gate_db=40), noisy)
    y = y[LATENCY_SAMPLES:]
    n = min(len(y), len(clean)) // 480 * 480
    ec, en, ey = frame_db(clean[:n]), frame_db(noise[:n]), frame_db(y[:n])
    audible = ec > en  # speech louder than the noise in that 10 ms frame
    ratio = ey - ec
    ratio -= np.median(ratio[ec > en + 6])
    cut = np.mean(ratio[audible] < -10)
    assert cut < 0.05, f"{100 * cut:.1f}% of audible speech frames cut"


def test_speech_gate_opens_during_speech() -> None:
    proc = DeepFilterNetProcessor(speech_atten_lim_db=20, pause_gate_db=40)
    run(proc, mix(padded(), white(len(padded())), 10)[: 6 * 48000])
    assert proc.speech_active


def test_reset_close_and_arguments() -> None:
    x = mix(speech(48000), white(len(speech(48000))), 5)[:24000]
    proc = DeepFilterNetProcessor()
    a = run(proc, x)
    proc.reset()
    np.testing.assert_allclose(run(proc, x), a, atol=1e-6)
    proc.close()
    with pytest.raises(BackendError, match="closed"):
        proc.process(np.zeros((1, 480), np.float32))
    with pytest.raises(BackendError):
        DeepFilterNetProcessor(channels=3)
    with pytest.raises(BackendError):
        DeepFilterNetProcessor(pause_gate_db=-1)


def test_stereo() -> None:
    x = speech(48000)[:48000]
    proc = DeepFilterNetProcessor(channels=2)
    st = np.stack([x, np.zeros_like(x)])
    out = np.concatenate([proc.process(st[:, i : i + 480]) for i in range(0, 48000, 480)], axis=1)
    np.testing.assert_allclose(out[0], run(DeepFilterNetProcessor(), x), atol=1e-5)
    assert np.max(np.abs(out[1])) < 1e-3
