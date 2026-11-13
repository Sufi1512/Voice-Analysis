"""Silero VAD feature and speech-gated noise suppression."""

import numpy as np

from nexora_audio import NexoraAudio
from nexora_audio.backends import silero
from nexora_audio.backends.rnnoise import RNNoiseProcessor
from tests.audio_fixtures import mix, pink, speech


def padded_speech(rate: int, pad_s: float = 2.0) -> np.ndarray:
    z = np.zeros(int(pad_s * rate), np.float32)
    return np.concatenate([z, speech(rate), z])


def test_probe_and_capability() -> None:
    assert silero.probe() is None
    caps = NexoraAudio().capabilities()["vad"]
    assert caps.available and caps.backend == "silero-vad"


def test_vad_events_follow_speech() -> None:
    x = padded_speech(16000)
    with NexoraAudio(
        sample_rate=16000, vad=True, noise_cancellation=False, voice_enhancement=False
    ) as a:
        for i in range(0, len(x), 160):
            a.process_chunk(x[i : i + 160])
        res = a.pop_results()
    events = [(r.start_sample / 16000, r.values["event"]) for r in res if r.values["event"]]
    # first word starts at 2.32 s (0.32 s into the clip, after 2 s of padding)
    assert events[0][1] == "speech_start" and 2.30 < events[0][0] < 2.45
    assert events[-1][1] == "speech_end" and 12.9 < events[-1][0] < 14.0
    probs = np.array([r.values["probability"] for r in res])
    t = np.array([r.start_sample / 16000 for r in res])
    assert probs[t < 1.8].max() < 0.2  # silence
    assert np.mean(probs[(t > 3) & (t < 12)] > 0.5) > 0.6  # mostly speech


def run(proc: RNNoiseProcessor, x: np.ndarray) -> np.ndarray:
    n = len(x) // 480 * 480
    return np.concatenate([proc.process(x[None, i : i + 480])[0] for i in range(0, n, 480)])


def test_gate_cleans_pauses_but_protects_speech() -> None:
    clean = padded_speech(48000)
    noisy = mix(clean, pink(len(clean)), 15)
    flat = run(RNNoiseProcessor(strength=0.85), noisy)
    gated = run(RNNoiseProcessor(strength=1.0, speech_strength=0.85), noisy)
    pause = slice(int(0.6 * 48000), 2 * 48000)
    level = lambda y: 10 * np.log10(np.mean(y[pause] ** 2) + 1e-20)  # noqa: E731
    assert level(gated) < level(flat) - 20  # pauses far cleaner than flat blending
    proc = RNNoiseProcessor(strength=1.0, speech_strength=0.85)
    run(proc, noisy[: 6 * 48000])
    assert proc.speech_active  # gate is open in the middle of speech


def test_gate_off_without_speech_strength() -> None:
    proc = RNNoiseProcessor(strength=1.0)
    assert not proc.speech_active
