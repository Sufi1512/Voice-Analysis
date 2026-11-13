import hashlib

import numpy as np
import pytest

from nexora_audio import AudioFormatError, TurnConfig
from nexora_audio.streaming.codecs import (
    AudioFormat,
    StreamDecoder,
    alaw_decode,
    alaw_encode,
    encode,
    mulaw_decode,
    mulaw_encode,
)
from nexora_audio.streaming.turns import TurnTracker

ALL16 = np.arange(-32768, 32768, dtype=np.int16)
ALL8 = np.arange(256, dtype=np.uint8)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


class TestG711:
    """Hashes are of CPython's audioop output (lin2ulaw/lin2alaw/ulaw2lin/alaw2lin) over
    every possible input, recorded on Python 3.11, so this is a bit-exact check."""

    def test_mulaw_matches_reference(self) -> None:
        assert sha(mulaw_encode(ALL16).tobytes()) == (
            "81d633c9e6972a18c74a58720b96cb8ca0bdd096d4060b646dd708c3b846019a"
        )
        assert sha(mulaw_decode(ALL8).astype("<i2").tobytes()) == (
            "3dab54339e520bb2c924826e3b72a917a2b612e9fd12fc867500f1d983a75827"
        )

    def test_alaw_matches_reference(self) -> None:
        assert sha(alaw_encode(ALL16).tobytes()) == (
            "38488f6fd710f4686360edc4d38639f96c491595ef93f8eb8d62d5e07ca6ce7b"
        )
        assert sha(alaw_decode(ALL8).astype("<i2").tobytes()) == (
            "e04788d110e58ff8c70c93b8480190d973e3b67876b6119abbaec766cc75c174"
        )


class TestStreamCodec:
    @pytest.mark.parametrize("enc", ["pcm16", "float32", "mulaw", "alaw"])
    def test_roundtrip_with_odd_chunking(self, enc: str) -> None:
        fmt = AudioFormat(enc, 16000, 2)  # type: ignore[arg-type]
        x = (np.random.default_rng(0).uniform(-0.5, 0.5, (2, 1000))).astype(np.float32)
        data = encode(x, fmt)
        dec = StreamDecoder(fmt)
        parts = [dec.decode(data[i : i + 7]) for i in range(0, len(data), 7)]  # split mid-sample
        y = np.concatenate(parts, axis=1)
        tol = {"pcm16": 1 / 32768, "float32": 0, "mulaw": 0.02, "alaw": 0.02}[enc]
        np.testing.assert_allclose(y, x, atol=tol + 1e-7)

    def test_format_validation(self) -> None:
        with pytest.raises(AudioFormatError):
            AudioFormat("mp3")  # type: ignore[arg-type]
        with pytest.raises(AudioFormatError):
            AudioFormat(channels=3)
        assert AudioFormat("mulaw", 8000).bytes_for_ms(20) == 160

    def test_rejects_nan_float_stream(self) -> None:
        with pytest.raises(AudioFormatError):
            StreamDecoder(AudioFormat("float32")).decode(np.array([np.nan], "<f4").tobytes())


def feed(t: TurnTracker, pattern: list[tuple[float, float]]) -> list[tuple[str, float]]:
    """pattern: (probability, duration_ms) segments, fed as 32 ms windows."""
    out, now = [], 0.0
    for prob, dur in pattern:
        for _ in range(round(dur / 32)):
            out += [(e.type, e.time_ms) for e in t.update(now, prob)]
            now += 32
    return out


class TestTurnTracker:
    def test_user_turn(self) -> None:
        ev = feed(TurnTracker(), [(0.0, 320), (0.9, 1600), (0.0, 1000)])
        assert [e[0] for e in ev] == ["speech_start", "speech_end", "end_of_turn"]
        assert ev[0][1] == pytest.approx(320)
        assert ev[2][1] - ev[1][1] == pytest.approx(704, abs=33)

    def test_short_pause_does_not_end_turn(self) -> None:
        ev = feed(TurnTracker(), [(0.9, 800), (0.0, 400), (0.9, 800), (0.0, 1000)])
        assert [e[0] for e in ev].count("end_of_turn") == 1

    def test_blip_is_ignored(self) -> None:
        assert feed(TurnTracker(), [(0.9, 32), (0.0, 1000)]) == []

    def test_interruption_while_agent_speaks(self) -> None:
        t = TurnTracker()
        t.set_agent_speaking(True)
        ev = feed(t, [(0.0, 320), (0.9, 1000), (0.0, 1000)])
        types = [e[0] for e in ev]
        assert "interruption" in types and "backchannel" not in types
        intr = dict(ev)["interruption"]
        assert intr - 320 == pytest.approx(TurnConfig().interruption_min_ms, abs=33)

    def test_backchannel_while_agent_speaks(self) -> None:
        t = TurnTracker()
        t.set_agent_speaking(True)
        ev = feed(t, [(0.0, 320), (0.9, 256), (0.0, 1000)])
        types = [e[0] for e in ev]
        assert "backchannel" in types
        assert "interruption" not in types and "end_of_turn" not in types

    def test_no_interruption_events_when_agent_silent(self) -> None:
        ev = feed(TurnTracker(), [(0.9, 1000), (0.0, 1000)])
        assert "interruption" not in [e[0] for e in ev]
