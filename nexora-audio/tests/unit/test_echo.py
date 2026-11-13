"""Echo reference timeline and echo-aware barge-in gate."""

import numpy as np

from nexora_audio.streaming.echo import EchoGate, ReferenceTimeline

RATE = 16000
HOP = RATE // 100


def speechy(seconds: float, seed: int) -> np.ndarray:
    """Noise with a random syllable-like on/off envelope."""
    rng = np.random.default_rng(seed)
    n = int(seconds * RATE)
    env = np.repeat(rng.random(n // 1600 + 1) > 0.4, 1600)[:n]
    return (0.1 * env * rng.standard_normal(n)).astype(np.float32)


def test_timeline_queues_bursts_in_playout_order() -> None:
    t = ReferenceTimeline(RATE)
    a, b = np.ones(1600, np.float32), 2 * np.ones(800, np.float32)
    t.push(a, now=0)
    t.push(b, now=100)  # sent while a is still playing: queued behind it
    assert t.queued_until == 2400
    got = t.get(1500, 200)
    assert np.all(got[:100] == 1) and np.all(got[100:] == 2)
    assert not t.get(5000, 10).any()  # nothing queued there


def run_gate(mic: np.ndarray, ref: np.ndarray) -> EchoGate:
    g = EchoGate(RATE)
    for i in range(0, len(mic) - HOP + 1, HOP):
        g.update(mic[i : i + HOP], ref[i : i + HOP])
    return g


def test_gate_learns_delay_and_flags_echo_only() -> None:
    ref = speechy(6.0, 1)
    delay = int(0.15 * RATE)
    echo = 0.5 * np.concatenate([np.zeros(delay, np.float32), ref[:-delay]])
    g = run_gate(echo, ref)
    assert g.learned and abs(g.delay_hops - 15) <= 1
    flagged = [g.is_echo(t, 0.032) for t in np.arange(3.0, 5.5, 0.05)]
    assert np.mean(flagged) > 0.6  # echo-only audio is recognised as echo


def test_double_talk_is_not_echo() -> None:
    ref = speechy(6.0, 1)
    delay = int(0.15 * RATE)
    echo = 0.3 * np.concatenate([np.zeros(delay, np.float32), ref[:-delay]])
    caller = np.zeros_like(ref)
    caller[4 * RATE :] = 0.1 * np.sin(2 * np.pi * 200 * np.arange(2 * RATE) / RATE)
    end = int(4.6 * RATE)  # judged live, as the session does: no hindsight
    g = run_gate((echo + caller)[:end], ref[:end])
    talk = [g.is_echo(t, 0.032) for t in np.arange(4.1, 4.5, 0.05)]
    assert not any(talk)  # the caller starting to talk over the agent is speech


def test_headset_caller_is_never_taken_for_echo() -> None:
    ref = speechy(4.0, 2)
    rng = np.random.default_rng(3)
    mic = (0.001 * rng.standard_normal(len(ref))).astype(np.float32)  # headset: no echo
    mic[int(2.5 * RATE) :] += 0.05 * np.sin(2 * np.pi * 180 * np.arange(int(1.5 * RATE)) / RATE)
    g = run_gate(mic, ref)
    assert not any(g.is_echo(t, 0.032) for t in np.arange(2.6, 3.9, 0.05))
