"""Voice enhancer: filters, levelling, limiting, and the default end-to-end chain."""

import numpy as np
import pytest

from nexora_audio import NexoraAudio
from nexora_audio.backends.enhancer import VoiceEnhancer
from tests.audio_fixtures import mix, speech, white
from tests.helpers import sine


def run(proc: VoiceEnhancer, x: np.ndarray) -> np.ndarray:
    x = np.atleast_2d(x).astype(np.float32)
    n = x.shape[1] // 480 * 480
    return np.concatenate([proc.process(x[:, i : i + 480]) for i in range(0, n, 480)], axis=1)


def level_db(x: np.ndarray) -> float:
    return float(20 * np.log10(np.sqrt(np.mean(np.square(x, dtype=np.float64)))))


def eq_only() -> VoiceEnhancer:
    return VoiceEnhancer(agc_target_dbfs=None, ceiling_dbfs=None)


def test_highpass_removes_rumble_keeps_voice_band() -> None:
    rumble = run(eq_only(), sine(30, 48000, 1.0, 0.3))[:, 24000:]
    voice = run(eq_only(), sine(500, 48000, 1.0, 0.3))[:, 24000:]
    assert level_db(rumble) < level_db(sine(30, 48000, 1.0, 0.3)) - 15
    assert abs(level_db(voice) - level_db(sine(500, 48000, 1.0, 0.3))) < 1.0


def test_clarity_boost_around_3khz() -> None:
    ref = level_db(sine(3000, 48000, 1.0, 0.1))
    boosted = level_db(run(eq_only(), sine(3000, 48000, 1.0, 0.1))[:, 24000:])
    assert boosted - ref == pytest.approx(3.0, abs=0.3)


def test_leveler_evens_out_quiet_and_loud_speech() -> None:
    s = speech(48000)
    parts = [s * 10 ** (g / 20) for g in (-15, 0, -6)]  # very quiet, normal, quiet talker
    y = run(VoiceEnhancer(), np.concatenate(parts))[0]
    n = len(s)
    before = [level_db(p) for p in parts]
    # measure the last two thirds of each part, after the gain has settled
    after = [level_db(y[i * n + n // 3 : (i + 1) * n]) for i in range(3)]
    assert max(before) - min(before) == pytest.approx(15, abs=0.5)
    assert max(after) - min(after) < 6.0
    assert all(abs(a - (-20)) < 6 for a in after)


def test_never_boosts_pauses_or_pure_noise() -> None:
    proc = VoiceEnhancer()
    run(proc, white(48000 * 3) * 0.003)  # steady low noise, no speech
    assert proc.gain_db <= 0.5


def test_limiter_prevents_clipping() -> None:
    loud = np.clip(speech(48000) * 4.0, -1, 1)
    y = run(VoiceEnhancer(agc_target_dbfs=-3.0, max_gain_db=15.0), loud)
    assert np.max(np.abs(y)) <= 10 ** (-1 / 20) + 1e-6


def test_stereo_shares_gain() -> None:
    s = speech(48000)[:96000]
    y = run(VoiceEnhancer(channels=2), np.stack([s, 0.5 * s]))
    np.testing.assert_allclose(y[1], 0.5 * y[0], atol=1e-5)


def test_default_chain_output_is_clean_level_and_unclipped() -> None:
    """Noise cancellation + enhancement with AGC switched on."""
    clean = speech(16000)
    noisy = mix(clean, white(len(clean)), 5) * 0.1  # quiet, noisy talker (about -35 dBFS)
    with NexoraAudio(sample_rate=16000, auto_gain_control=True) as a:
        from nexora_audio.backends import deepfilternet as dfn

        engine = "deepfilternet3" if dfn.probe() is None else "rnnoise"  # the fallback
        assert a.backends == [engine, "voice-enhancer"]
        y = np.concatenate([a.process_chunk(noisy[i : i + 160]) for i in range(0, len(noisy), 160)])
    assert level_db(y[len(y) // 3 :]) > level_db(noisy) + 6  # quiet voice brought up
    assert np.max(np.abs(y)) <= 10 ** (-1 / 20) + 1e-6
