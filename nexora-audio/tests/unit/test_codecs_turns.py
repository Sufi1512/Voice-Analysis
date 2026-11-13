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


class TestSmartTurnJudge:
    """The tracker with a judge: finished-sounding turns end after complete_silence_ms,
    unfinished ones wait incomplete_silence_ms; a missing or failing judge falls back."""

    CFG = TurnConfig(complete_silence_ms=300, incomplete_silence_ms=2000)

    def eot_gap(self, judge: object, cfg: TurnConfig = CFG) -> float | None:
        t = TurnTracker(cfg, judge=judge)  # type: ignore[arg-type]
        ev = feed(t, [(0.0, 320), (0.9, 1600), (0.0, 3000)])
        last_voice = dict(ev)["speech_end"]
        eot = [time for kind, time in ev if kind == "end_of_turn"]
        return eot[0] - last_voice if eot else None

    def test_finished_turn_ends_fast(self) -> None:
        assert self.eot_gap(lambda a, b: 0.9) == pytest.approx(320, abs=33)

    def test_unfinished_turn_waits(self) -> None:
        assert self.eot_gap(lambda a, b: 0.1) == pytest.approx(2016, abs=33)

    def test_unsure_or_broken_judge_uses_plain_rule(self) -> None:
        def broken(a: float, b: float) -> float:
            raise RuntimeError("model gone")

        assert self.eot_gap(lambda a, b: None) == pytest.approx(704, abs=33)
        assert self.eot_gap(broken) == pytest.approx(704, abs=33)

    def test_judge_sees_turn_up_to_last_voice(self) -> None:
        spans: list[tuple[float, float]] = []
        t = TurnTracker(self.CFG, judge=lambda a, b: spans.append((a, b)) or 0.9)
        feed(t, [(0.0, 800), (0.9, 1600), (0.0, 1000)])
        ((a, b),) = spans
        assert a == pytest.approx(800 - self.CFG.pre_speech_ms, abs=33)
        assert b == pytest.approx(2400, abs=33)  # the last voiced window, not the silence

    def test_resumed_speech_is_one_turn_and_rejudged(self) -> None:
        verdicts = iter([0.1, 0.9])
        t = TurnTracker(self.CFG, judge=lambda a, b: next(verdicts))
        ev = feed(t, [(0.9, 800), (0.0, 1200), (0.9, 800), (0.0, 1000)])
        types = [e[0] for e in ev]
        assert types.count("end_of_turn") == 1  # the 1.2 s pause sounded unfinished
        assert types.count("speech_end") == 2

    def test_probability_in_event(self) -> None:
        t = TurnTracker(self.CFG, judge=lambda a, b: 0.876)
        events = []
        now = 0.0
        for p, dur in [(0.9, 800), (0.0, 1000)]:
            for _ in range(round(dur / 32)):
                events += t.update(now, p)
                now += 32
        eot = next(e for e in events if e.type == "end_of_turn")
        assert eot.to_dict()["complete_probability"] == 0.876


def test_smart_turn_model_judges_real_speech() -> None:
    from nexora_audio.backends import smart_turn

    if smart_turn.probe() is not None:
        pytest.skip(smart_turn.probe())
    rng = np.random.default_rng(1)
    p = smart_turn.complete_probability(rng.standard_normal(16000).astype(np.float32) * 0.01)
    assert 0.0 <= p <= 1.0
    assert hashlib.sha256(smart_turn.model_path().read_bytes()).hexdigest() == (
        "2bb026316b14a660486a75b1733cd3fbab8c2fd0314dc9af7be49f8cca967e4f"
    )
