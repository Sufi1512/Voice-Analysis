"""T4: the `nexora` engine meets the same contract as Dograh's RNNoise engine (AC-4, AC-5).

Built through Dograh's real factory, so every test also covers the patch wiring. Uses the
default nexora-audio settings (what a call gets when NEXORA_AUDIO_SETTINGS is unset).
Signals: seeded white noise, and the speech recording that ships in Dograh's Pipecat fork.
"""

import time
import wave

import numpy as np
import pytest
from pipecat.frames.frames import FilterEnableFrame
from scipy.signal import resample_poly

from api.constants import APP_ROOT_DIR
from api.services.pipecat.noise_reduction.factory import build_audio_in_filter
from api.services.pipecat.noise_reduction.safe_filter import DEFAULT_FRAME_BUDGET_MS, SafeAudioFilter

NEXORA = {"enabled": True, "engine": "nexora"}
RATES = [8000, 16000]
SPEECH_WAV = APP_ROOT_DIR.parent / "pipecat/scripts/provider-watch/assets/speech-16k.wav"


@pytest.fixture(autouse=True)
def default_settings(monkeypatch):
    monkeypatch.delenv("NEXORA_AUDIO_SETTINGS", raising=False)


def noise(rate: int, seconds: float, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return (rng.standard_normal(int(rate * seconds)) * 1000).astype(np.int16)


def speech(rate: int) -> np.ndarray:
    with wave.open(str(SPEECH_WAV)) as wav:
        assert wav.getframerate() == 16000 and wav.getnchannels() == 1
        samples = np.frombuffer(wav.readframes(wav.getnframes()), dtype=np.int16)
    if rate == 16000:
        return samples
    return np.clip(resample_poly(samples.astype(np.float64), rate, 16000), -32768, 32767).astype(np.int16)


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x.astype(np.float64) ** 2))) if len(x) else 0.0


def db(ratio: float) -> float:
    return 20 * np.log10(max(ratio, 1e-12))


async def run(filt, audio: np.ndarray, rate: int, chunk: int | None = None):
    """Feed 20 ms chunks (or ``chunk`` samples); return output and per-chunk seconds."""
    chunk = chunk or rate // 50
    out, times = [], []
    for i in range(0, len(audio), chunk):
        t0 = time.perf_counter()
        out.append(await filt.filter(audio[i : i + chunk].tobytes()))
        times.append(time.perf_counter() - t0)
    return np.frombuffer(b"".join(out), dtype=np.int16), times


async def started(rate: int) -> SafeAudioFilter:
    filt = build_audio_in_filter(NEXORA)
    await filt.start(rate)
    return filt


# --- AC-4: factory -----------------------------------------------------------


def test_factory_wraps_nexora_in_safe_filter():
    from nexora_audio.integrations.pipecat import NexoraAudioFilter

    filt = build_audio_in_filter(NEXORA)
    assert isinstance(filt, SafeAudioFilter)
    assert isinstance(filt._engine, NexoraAudioFilter)  # noqa: SLF001


def test_new_instance_per_call():
    first, second = build_audio_in_filter(NEXORA), build_audio_in_filter(NEXORA)
    assert first is not second
    assert first._engine is not second._engine  # noqa: SLF001


# --- AC-5: contract -----------------------------------------------------------


@pytest.mark.parametrize("rate", RATES)
async def test_keeps_pace(rate):
    filt = await started(rate)
    audio = noise(rate, 2.0)
    out, _ = await run(filt, audio, rate)
    await filt.stop()
    missing = len(audio) - len(out)
    assert 0 <= missing <= rate // 10, f"{missing} samples behind (more than 100 ms)"


@pytest.mark.parametrize("rate", RATES)
async def test_removes_stationary_noise(rate):
    filt = await started(rate)
    audio = noise(rate, 3.0)
    out, _ = await run(filt, audio, rate)
    await filt.stop()
    # after one second of adaptation
    reduction = db(rms(out[rate:]) / rms(audio[rate:]))
    assert reduction <= -10, f"noise only reduced by {-reduction:.1f} dB"


@pytest.mark.parametrize("rate", RATES)
async def test_keeps_clean_speech(rate):
    filt = await started(rate)
    audio = speech(rate)
    out, _ = await run(filt, audio, rate)
    await filt.stop()
    skip = rate // 2
    change = db(rms(out[skip:]) / rms(audio[skip : skip + len(out[skip:])]))
    assert abs(change) <= 3, f"clean speech level changed by {change:+.1f} dB"


async def test_disable_frame_passes_through():
    rate = 8000
    filt = await started(rate)
    await filt.process_frame(FilterEnableFrame(enable=False))
    audio = noise(rate, 0.5)
    out, _ = await run(filt, audio, rate)
    await filt.stop()
    assert np.array_equal(out, audio)


@pytest.mark.parametrize("chunk", [1, 37, 160, 333, 1600])
async def test_any_chunk_size(chunk):
    rate = 8000
    filt = await started(rate)
    audio = noise(rate, 1.0)
    out, _ = await run(filt, audio, rate, chunk=chunk)
    await filt.stop()
    assert out.dtype == np.int16
    assert len(audio) - len(out) <= rate // 10


async def test_passes_audio_outside_start_stop():
    rate = 8000
    filt = build_audio_in_filter(NEXORA)
    audio = noise(rate, 0.1)
    before, _ = await run(filt, audio, rate)
    await filt.start(rate)
    await run(filt, noise(rate, 0.5, seed=1), rate)
    await filt.stop()
    after, _ = await run(filt, audio, rate)
    assert np.array_equal(before, audio)
    assert np.array_equal(after, audio)


@pytest.mark.parametrize("rate", RATES)
async def test_under_safe_filter_budget(rate):
    filt = await started(rate)
    _, times = await run(filt, noise(rate, 5.0), rate)
    await filt.stop()
    ms = np.array(times[5:]) * 1000  # skip warm-up chunks
    p95, worst = float(np.percentile(ms, 95)), float(ms.max())
    print(f"\nnexora at {rate} Hz: p95 {p95:.2f} ms, max {worst:.2f} ms, budget {DEFAULT_FRAME_BUDGET_MS} ms")
    assert filt.disabled_reason is None, filt.disabled_reason
    assert p95 < DEFAULT_FRAME_BUDGET_MS
