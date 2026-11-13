"""Test corpus v1: deterministic cases built from pinned speech/noise and synthetic signals.

Sets (see VOICE_QUALITY_PLAN.md, "How we prove it"):

* ``clean``  - speech only: processing must not harm it.
* ``noise``  - speech + real and synthetic noise across SNRs.
* ``phone``  - the same through a 300-3400 Hz, 8 kHz G.711 mu-law phone line.
* ``reverb`` - reverberant room speech + noise.
* ``loss``   - packet loss (no concealment today), paired with a loss-free twin.
* ``echo``   - agent audio leaking back through a speakerphone, single- and double-talk.
* ``turns``  - speech with mid-sentence pauses, to measure cut-offs and reply delay.
"""

from __future__ import annotations

import zlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from qualitylab import sources, synth

RATE = 16000
LEAD_S = 2.0
TAIL_S = 1.5
SPEECH_DBFS = -26.0


@dataclass
class Case:
    id: str
    set: str
    rate: int
    mic: np.ndarray  # what the pipeline receives (float32 at ``rate``)
    clean: np.ndarray  # near-end speech reference, aligned with ``mic``
    noise: np.ndarray | None = None  # noise component of ``mic``
    echo: np.ndarray | None = None  # echo component of ``mic``
    reference: np.ndarray | None = None  # agent audio sent to the caller (echo reference)
    encoding: str = "pcm16"
    speech_span: tuple[float, float] = (0.0, 0.0)  # seconds, near-end speech
    agent_spans: list[tuple[float, float]] = field(default_factory=list)
    labels: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)
    stt: bool = False

    @property
    def seconds(self) -> float:
        return len(self.mic) / self.rate


def seed_of(*parts: object) -> int:
    return zlib.crc32("/".join(map(str, parts)).encode()) & 0x7FFFFFFF


def _level(x: np.ndarray, dbfs: float = SPEECH_DBFS) -> np.ndarray:
    return (x * np.sqrt(10 ** (dbfs / 10) / synth.active_power(x))).astype(np.float32)


def _pad(x: np.ndarray, lead: float = LEAD_S, tail: float = TAIL_S) -> np.ndarray:
    return np.concatenate(
        [np.zeros(int(lead * RATE), np.float32), x, np.zeros(int(tail * RATE), np.float32)]
    )


def _noise(name: str, n: int, seed: int) -> np.ndarray:
    if name in synth.SYNTH_NOISES:
        return synth.synth_noise(name, n, RATE, seed)
    return synth.fit(sources.real_noise(name, seed % 2), n, seed)


def _span(speech: np.ndarray) -> tuple[float, float]:
    return LEAD_S, LEAD_S + len(speech) / RATE


def noise_case(set_: str, clip: str, speech: np.ndarray, noise: str, snr: float) -> Case:
    s = _pad(_level(speech))
    nz = synth.scale_to_snr(s, _noise(noise, len(s), seed_of(clip, noise)), snr)
    return Case(
        f"{set_}/{noise}/{snr:+g}dB/{clip}",
        set_,
        RATE,
        (s + nz).astype(np.float32),
        s,
        nz,
        speech_span=_span(speech),
        meta={"noise": noise, "snr": snr, "clip": clip},
        stt=True,
    )


def clean_case(clip: str, speech: np.ndarray) -> Case:
    s = _pad(_level(speech))
    return Case(
        f"clean/{clip}",
        "clean",
        RATE,
        s.copy(),
        s,
        np.zeros_like(s),
        speech_span=_span(speech),
        meta={"clip": clip},
        stt=True,
    )


def phone_case(clip: str, speech: np.ndarray, noise: str | None, snr: float) -> Case:
    s = _pad(_level(speech))
    nz = (
        synth.scale_to_snr(s, _noise(noise, len(s), seed_of(clip, noise, "phone")), snr)
        if noise
        else np.zeros_like(s)
    )
    mic8, _ = synth.phone_line(s + nz, "mulaw")
    label = f"{noise}/{snr:+g}dB" if noise else "clean"
    return Case(
        f"phone/{label}/{clip}",
        "phone",
        8000,
        mic8,
        synth.band8k(s),
        synth.band8k(nz),
        encoding="mulaw",
        speech_span=_span(speech),
        meta={"noise": noise or "none", "snr": snr if noise else None, "clip": clip},
        stt=True,
    )


def reverb_case(clip: str, speech: np.ndarray, rt60: float) -> Case:
    wet = synth.reverb(_level(speech), synth.room_ir(RATE, rt60, seed_of(clip, rt60)))
    s = _pad(wet)
    nz = synth.scale_to_snr(s, _noise("pink", len(s), seed_of(clip, "rv")), 10)
    return Case(
        f"reverb/rt60_{rt60}s/{clip}",
        "reverb",
        RATE,
        (s + nz).astype(np.float32),
        s,
        nz,
        speech_span=_span(speech),
        meta={"rt60": rt60, "clip": clip, "snr": 10},
        stt=True,
    )


def loss_cases(clip: str, speech: np.ndarray, loss_pct: float) -> list[Case]:
    base = noise_case("loss", clip, speech, "pink", 10)
    mask = synth.gilbert_loss(len(base.mic) // 320 + 1, loss_pct, seed_of(clip, loss_pct))
    lossy = synth.apply_loss(base.mic, RATE, mask)
    twin = f"loss/0%/{clip}"
    base.id, base.meta = twin, {**base.meta, "loss_pct": 0.0, "pair": twin}
    case = Case(
        f"loss/{loss_pct:g}%/{clip}",
        "loss",
        RATE,
        lossy,
        base.clean,
        base.noise,
        speech_span=base.speech_span,
        stt=True,
        meta={**base.meta, "loss_pct": loss_pct, "pair": twin, "lost_fraction": float(mask.mean())},
    )
    return [base, case]


def echo_case(
    clip_agent: str,
    agent: np.ndarray,
    clip_near: str | None,
    near: np.ndarray | None,
    delay_ms: float,
    echo_db: float | None,
    interrupt_s: float = 3.5,
) -> Case:
    """Agent talks from 1.0 s; with ``near`` the caller starts talking at ``interrupt_s``.
    ``echo_db=None``: no echo at all (a headset, or a device that cancels it)."""
    ref = np.concatenate([np.zeros(RATE), _level(agent), np.zeros(int(2.5 * RATE))])
    n = len(ref)
    agent_span = (1.0, 1.0 + len(agent) / RATE)
    echo = synth.echo_path(ref, RATE, delay_ms, seed_of(clip_agent, delay_ms))
    if echo_db is None:
        echo = np.zeros_like(echo)
    else:
        echo = echo * np.sqrt(10 ** ((SPEECH_DBFS + echo_db) / 10) / synth.active_power(echo))
    clean = np.zeros(n, np.float32)
    span = (0.0, 0.0)
    kind = "single"
    if near is not None:
        kind = "double"
        start = int(interrupt_s * RATE)
        seg = _level(near)[: n - start - RATE // 2]
        clean[start : start + len(seg)] = seg
        span = (start / RATE, (start + len(seg)) / RATE)
    floor = synth.scale_to_snr(_level(agent), _noise("pink", n, seed_of("echo", clip_agent)), 45)
    mic = (clean + echo + floor).astype(np.float32)
    return Case(
        f"echo/{kind}/{delay_ms:g}ms/{'none' if echo_db is None else f'{echo_db:+g}dB'}"
        f"{'' if interrupt_s == 3.5 else f'/at{interrupt_s:g}s'}/{clip_agent}",
        "echo",
        RATE,
        mic,
        clean,
        floor.astype(np.float32),
        echo.astype(np.float32),
        ref.astype(np.float32),
        speech_span=span,
        agent_spans=[agent_span],
        meta={
            "kind": kind,
            "delay_ms": delay_ms,
            "echo_db": echo_db,
            "agent_clip": clip_agent,
            "near_clip": clip_near,
        },
    )


def turn_case(clip: str, speech: np.ndarray, pauses_ms: list[float]) -> Case:
    """Insert silent pauses at the quietest word gaps; the turn really ends after the clip."""
    x = _level(speech)
    hop = RATE // 50
    e = np.convolve(
        np.mean(x[: len(x) // hop * hop].reshape(-1, hop) ** 2, axis=1), np.ones(5) / 5, mode="same"
    )
    cuts: list[int] = []
    for k, _ in enumerate(pauses_ms):
        lo, hi = (
            len(e) * (k + 1) // (len(pauses_ms) + 1) - len(e) // 8,
            len(e) * (k + 1) // (len(pauses_ms) + 1) + len(e) // 8,
        )
        cuts.append((lo + int(np.argmin(e[lo:hi]))) * hop)
    parts, pauses, t, prev = [], [], LEAD_S, 0
    for cut, ms in zip(cuts, pauses_ms, strict=True):
        parts.append(x[prev:cut])
        t += (cut - prev) / RATE
        pauses.append((t, t + ms / 1000))
        parts.append(np.zeros(int(ms / 1000 * RATE), np.float32))
        t += ms / 1000
        prev = cut
    parts.append(x[prev:])
    body = np.concatenate(parts)
    s = _pad(body, tail=3.0)
    nz = synth.scale_to_snr(s, _noise("pink", len(s), seed_of(clip, "turn")), 25)
    end = LEAD_S + len(body) / RATE
    return Case(
        f"turns/{clip}",
        "turns",
        RATE,
        (s + nz).astype(np.float32),
        s,
        nz,
        speech_span=(LEAD_S, end),
        labels={"pauses": pauses, "true_end": end},
        meta={"clip": clip, "pauses_ms": pauses_ms},
    )


# -- profiles -----------------------------------------------------------------------


def _clips() -> tuple[list[str], dict[str, np.ndarray]]:
    clips = sources.speech_clips()
    if len(clips) < 2:
        raise RuntimeError("test audio missing: run `python -m qualitylab fetch` first")
    return list(clips), clips


def build(profile: str) -> Iterator[Case]:
    names, clips = _clips()

    def clip(i: int) -> str:
        return names[i % len(names)]

    if profile == "fast":
        noise_plan = [
            ("white", 0),
            ("pink", 10),
            ("babble", 5),
            ("typing", 10),
            ("air_conditioner", 0),
            ("neighbor", 10),
        ]
        for i, (nz, snr) in enumerate(noise_plan):
            yield noise_case("noise", clip(i), clips[clip(i)], nz, snr)
        for i in range(2):
            yield clean_case(clip(i), clips[clip(i)])
        yield phone_case(clip(1), clips[clip(1)], "babble", 10)
        yield phone_case(clip(2), clips[clip(2)], "air_conditioner", 5)
        yield reverb_case(clip(3), clips[clip(3)], 0.5)
        yield from loss_cases(clip(4), clips[clip(4)], 5)
        yield echo_case(clip(5), clips[clip(5)], None, None, 120, 0)
        yield echo_case(clip(6), clips[clip(6)], clip(7), clips[clip(7)], 120, 0)
        yield echo_case(clip(9), clips[clip(9)], clip(10), clips[clip(10)], 0, None)
        yield turn_case(clip(8), clips[clip(8)], [500, 900])
        return
    if profile != "full":
        raise ValueError(f"unknown profile {profile!r}")
    noises = list(sources.REAL_NOISES) + list(synth.SYNTH_NOISES)
    k = 0
    for nz in noises:
        for snr in (-5, 0, 5, 10, 20, 30):
            for _ in range(2):
                yield noise_case("noise", clip(k), clips[clip(k)], nz, snr)
                k += 1
    for i in range(8):
        yield clean_case(clip(i), clips[clip(i)])
    for j, nz in enumerate(["babble", "air_conditioner", "typing", "vacuum", "pink"]):
        for snr in (0, 10):
            yield phone_case(clip(j * 2 + snr), clips[clip(j * 2 + snr)], nz, snr)
    for i in range(2):
        yield phone_case(clip(20 + i), clips[clip(20 + i)], None, 0)
    for i, rt in enumerate([0.3, 0.3, 0.3, 0.6, 0.6, 0.6]):
        yield reverb_case(clip(i + 3), clips[clip(i + 3)], rt)
    for i, pct in enumerate([1, 3, 5, 10]):
        for j in range(2):
            c = clip(i * 2 + j + 11)
            yield from loss_cases(c, clips[c], pct)
    e = 0
    for delay in (40, 120, 250, 400):
        for edb in (6, 0, -10):
            a, b = clip(e + 5), clip(e + 6)
            yield echo_case(a, clips[a], None, None, delay, edb)
            yield echo_case(a, clips[a], b, clips[b], delay, edb)
            e += 2
    for i in range(2):  # headset: no echo, the caller must still be able to interrupt
        a, b = clip(i + 3), clip(i + 4)
        yield echo_case(a, clips[a], b, clips[b], 0, None)
    for i, edb in enumerate((0, -10)):  # interrupting in the agent's first second
        a, b = clip(i + 9), clip(i + 10)
        yield echo_case(a, clips[a], b, clips[b], 120, edb, interrupt_s=1.6)
    plans = [[400, 800], [600, 1000], [500, 1200], [700, 900]]
    for i in range(8):
        c = clip(i + 13)
        yield turn_case(c, clips[c], plans[i % len(plans)])
