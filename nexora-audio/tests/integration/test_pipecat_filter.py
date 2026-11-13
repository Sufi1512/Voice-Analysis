"""NexoraAudioFilter on real Pipecat classes (as Dograh uses it)."""

import asyncio

import numpy as np
import pytest

pytest.importorskip("pipecat")

from pipecat.audio.filters.base_audio_filter import BaseAudioFilter
from pipecat.frames.frames import FilterEnableFrame

from nexora_audio.integrations.pipecat import NexoraAudioFilter
from tests.audio_fixtures import mix, pink, speech

RATE = 8000  # Twilio-style telephony transport


def pcm(x: np.ndarray) -> bytes:
    return (np.clip(x, -1, 1) * 32767).astype("<i2").tobytes()


async def _run(f: NexoraAudioFilter, data: bytes, step: int) -> bytes:
    out = bytearray()
    for i in range(0, len(data), step):
        out += await f.filter(data[i : i + step])
    return bytes(out)


def test_filter_lifecycle_pacing_and_noise_removal() -> None:
    clean = np.concatenate([np.zeros(RATE, np.float32), speech(RATE), np.zeros(RATE, np.float32)])
    noisy = mix(clean, pink(len(clean)), 10)
    data = pcm(noisy)

    async def main() -> tuple[bytes, dict, bytes]:
        f = NexoraAudioFilter()
        assert isinstance(f, BaseAudioFilter)
        await f.start(RATE)
        out = await _run(f, data, 320)  # 20 ms frames
        q = f.quality()
        await f.process_frame(FilterEnableFrame(enable=False))
        passthrough = await f.filter(data[:320])
        await f.stop()
        return out, q, passthrough

    out, q, passthrough = asyncio.run(main())
    assert passthrough == data[:320]  # disabled: audio untouched
    lag = len(data) - len(out)
    assert 0 <= lag <= RATE * 2 * 0.1  # keeps pace: only the processing delay is held back
    y = np.frombuffer(out, "<i2").astype(np.float32) / 32768
    lead = slice(int(0.3 * RATE), int(0.9 * RATE))  # noise-only start
    assert np.mean(y[lead] ** 2) < 0.01 * np.mean(noisy[lead] ** 2)  # >20 dB cleaner pauses
    assert q["snr_db"] > 5 and q["latency_ms"] > 0


def test_settings_are_passed_through() -> None:
    async def main() -> list[str]:
        f = NexoraAudioFilter(noise_backend="rnnoise", offload=False)
        await f.start(16000)
        backends = f._session.backends if f._session else []
        await f.stop()
        return backends

    assert asyncio.run(main())[0] == "rnnoise"
