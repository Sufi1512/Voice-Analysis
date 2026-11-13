"""Background-talker gate."""

from nexora_audio.core.talker_gate import TalkerGate

F = 0.01  # 10 ms frames


def feed(g: TalkerGate, energy: float, frames: int, speech: bool = True) -> list[bool]:
    return [g.update(energy, speech) for _ in range(frames)]


def test_quiet_background_talk_is_flagged_after_learning_the_caller() -> None:
    g = TalkerGate(F)
    assert not any(feed(g, 1e-3, 150))  # caller at -30 dB: learned, never background
    flags = feed(g, 1e-6, 200)  # TV 30 dB below the caller
    assert not any(flags[:30])  # word endings are protected for a moment
    assert all(flags[120:])  # then it is background
    assert not any(feed(g, 1e-3, 50))  # caller again: not background at once
    assert g.background_frames > 0


def test_nothing_flagged_before_the_caller_is_known() -> None:
    g = TalkerGate(F)
    assert not any(feed(g, 1e-6, 50))  # under 1 s of speech: no judgement yet


def test_non_speech_is_never_background() -> None:
    g = TalkerGate(F)
    feed(g, 1e-3, 150)
    assert not any(feed(g, 1e-6, 100, speech=False))


def test_a_quieter_caller_takes_over_after_8_seconds() -> None:
    g = TalkerGate(F)
    feed(g, 1e-3, 150)
    flags = feed(g, 1e-6, 1000)  # a new, much quieter speaker talks for 10 s
    assert all(flags[150:700]) and not any(flags[-50:])
