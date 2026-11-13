"""StreamSession: bytes in/out, turn events on real speech, async and threads."""

import asyncio
import concurrent.futures

import numpy as np
import pytest
from scipy.signal import resample_poly

from nexora_audio import AudioFormat, ConfigurationError, StreamSession, TurnConfig
from nexora_audio.streaming.codecs import StreamDecoder, encode
from nexora_audio.streaming.opus import probe as opus_probe
from tests.audio_fixtures import mix, speech, white

PCM16 = AudioFormat("pcm16", 16000)


def padded_speech_bytes(fmt: AudioFormat, pad_s: float = 2.0, snr: float | None = 10) -> bytes:
    x = speech(16000)
    if fmt.sample_rate != 16000:
        g = np.gcd(fmt.sample_rate, 16000)
        x = resample_poly(x, fmt.sample_rate // g, 16000 // g).astype(np.float32)
    z = np.zeros(int(pad_s * fmt.sample_rate), np.float32)
    s = np.concatenate([z, x, z])
    if snr is not None:
        s = mix(s, white(len(s)), snr) if snr else s
    return encode(s[None, :] * 0.8, fmt)


def run(session: StreamSession, data: bytes, chunk_ms: float = 20) -> tuple[bytes, list]:
    step = session.input_format.bytes_for_ms(chunk_ms)
    audio, events = bytearray(), []
    for i in range(0, len(data), step):
        o = session.process(data[i : i + step])
        audio += o.audio
        events += o.events
    f = session.flush()
    return bytes(audio + f.audio), events + f.events


def test_pcm16_session_events_and_length() -> None:
    data = padded_speech_bytes(PCM16)
    with StreamSession(input_format=PCM16) as s:
        audio, events = run(s, data)
        assert s.backends[0] in ("deepfilternet3", "rnnoise") and "silero-vad" in s.backends
    assert len(audio) >= len(data)
    types = [e.type for e in events]
    assert types[0] == "speech_start" and types[-1] == "end_of_turn"
    assert 2250 < events[0].time_ms < 2500  # first word at 2.32 s
    last_end = [e for e in events if e.type == "speech_end"][-1]
    # the last word ends at ~12.45 s; crowd noise rises after it (a short blip there may or
    # may not be reported as speech)
    assert 12_300 < last_end.time_ms < 13_200


@pytest.mark.parametrize("enc", ["mulaw", "alaw"])
def test_telephony_8k(enc: str) -> None:
    fmt = AudioFormat(enc, 8000)  # type: ignore[arg-type]
    data = padded_speech_bytes(fmt)
    with StreamSession(input_format=fmt) as s:
        audio, events = run(s, data)
    assert len(audio) >= len(data)
    assert {"speech_start", "end_of_turn"} <= {e.type for e in events}


def test_output_format_conversion() -> None:
    out_fmt = AudioFormat("pcm16", 24000)
    data = padded_speech_bytes(PCM16, pad_s=0.5)
    with StreamSession(input_format=PCM16, output_format=out_fmt) as s:
        audio, _ = run(s, data)
    in_samples, out_samples = len(data) // 2, len(audio) // 2
    assert out_samples == pytest.approx(in_samples * 1.5, rel=0.02)


def test_interruption_and_backchannel() -> None:
    clip = speech(16000)
    word = clip[int(0.32 * 16000) : int(0.6 * 16000)]  # ~0.28 s of speech: a "backchannel"
    phrase = clip[int(0.32 * 16000) : int(2.0 * 16000)]  # 1.7 s of speech: a real interruption
    z = np.zeros(16000, np.float32)
    sig = np.concatenate([z, word, z, z, phrase, z, z])
    with StreamSession(input_format=PCM16) as s:
        s.set_agent_speaking(True)
        _, events = run(s, encode(sig[None, :] * 0.8, PCM16))
    types = [e.type for e in events]
    assert types.count("backchannel") == 1
    assert types.count("interruption") == 1
    assert types.index("backchannel") < types.index("interruption")


def test_turns_can_be_disabled_and_sessions_closed() -> None:
    s = StreamSession(input_format=PCM16, turns=None)
    assert "silero-vad" not in s.backends
    _, events = run(s, padded_speech_bytes(PCM16, pad_s=0.5))
    assert events == []
    s.close()
    with pytest.raises(ConfigurationError):
        s.process(b"\x00\x00")
    with pytest.raises(ConfigurationError):
        StreamSession(input_format=PCM16, output_format=AudioFormat("pcm16", 16000, 2))


def test_async_matches_sync() -> None:
    data = padded_speech_bytes(PCM16, pad_s=0.5)
    with StreamSession(input_format=PCM16) as s:
        sync_audio, _ = run(s, data)

    async def main() -> bytes:
        out = bytearray()
        async with StreamSession(input_format=PCM16) as s:
            step = PCM16.bytes_for_ms(20)
            for i in range(0, len(data), step):
                out += (await s.aprocess(data[i : i + step])).audio
            out += s.flush().audio
        return bytes(out)

    assert asyncio.run(main()) == sync_audio


def test_concurrent_sessions_are_independent() -> None:
    inputs = [padded_speech_bytes(PCM16, pad_s=0.3, snr=snr) for snr in (0, 5, 10, 20)]

    def one(data: bytes) -> bytes:
        with StreamSession(input_format=PCM16, turns=TurnConfig()) as s:
            return run(s, data)[0]

    sequential = [one(d) for d in inputs]
    with concurrent.futures.ThreadPoolExecutor(4) as ex:
        parallel = list(ex.map(one, inputs))
    assert parallel == sequential


def test_conceal_keeps_time_and_quality_reports() -> None:
    fmt = AudioFormat("pcm16", 16000)
    data = padded_speech_bytes(fmt)
    step = fmt.bytes_for_ms(20)
    out = bytearray()
    with StreamSession(input_format=fmt, turns=None) as s:
        for k, i in enumerate(range(0, len(data), step)):
            if k == 200:  # transport says this packet is missing: send nothing, conceal it
                out += s.conceal(20).audio
                continue
            out += s.process(data[i : i + step]).audio
        out += s.flush().audio
        q = s.quality()
    # concealing instead of dropping keeps the stream aligned: same length as a full stream
    # (flush() adds the delayed tail plus frame padding, under 100 ms)
    assert 0 <= len(out) - len(data) < fmt.bytes_for_ms(100)
    assert q["concealed_ms"] == 20.0 and q["loss_events"] == 1
    assert q["snr_db"] > 10  # the 1961 recording has its own crowd noise
    assert "chunk_p99_ms" in q and q["guard_restored_frames"] >= 0


@pytest.mark.skipif(opus_probe() is not None, reason="libopus not installed")
def test_opus_input_session() -> None:
    from nexora_audio.streaming.opus import OpusEncoder

    pcm = AudioFormat("pcm16", 16000)
    raw = padded_speech_bytes(pcm)
    x = StreamDecoder(pcm).decode(raw)
    enc = OpusEncoder(16000)
    with StreamSession(input_format=AudioFormat("opus", 16000)) as s:
        assert s.output_format == pcm
        audio = bytearray()
        events = []
        for i in range(0, x.shape[1] - 320, 320):
            o = s.process(enc.encode(x[:, i : i + 320]) if i // 320 != 300 else b"")
            audio += o.audio
            events += o.events
        audio += s.flush().audio
    assert {"speech_start", "end_of_turn"} <= {e.type for e in events}
    assert abs(len(audio) - (x.shape[1] // 320) * 640) < 3200
