"""E7: live device streaming on a simulated sound card (no PortAudio needed).

``FakeDuplex`` calls the callback at real-time pace with microphone audio, like a sound card
does, and records what was played. Real hardware: ``pytest -m device`` on your machine.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from typing import Any

import numpy as np
import pytest

from nexora_audio.devices import LiveSession, RingBuffer
from tests.audio_fixtures import pink, speech

RATE = 16000


# -- ring buffer -------------------------------------------------------------------------


def test_ring_wraps_and_counts_overflow() -> None:
    r = RingBuffer(10)
    assert r.write(np.arange(6, dtype=np.float32)) == 6
    np.testing.assert_array_equal(r.read(4), [0, 1, 2, 3])
    assert r.write(np.arange(6, 14, dtype=np.float32)) == 8  # wraps around the end
    np.testing.assert_array_equal(r.read(10), [4, 5, 6, 7, 8, 9, 10, 11, 12, 13])
    assert r.read(1) is None
    assert r.write(np.zeros(15, np.float32)) == 10 and r.dropped == 5


def test_ring_concurrent_producer_consumer_keeps_order() -> None:
    r = RingBuffer(997)  # odd size so blocks straddle the end
    total, got = 400_000, []

    def produce() -> None:
        i = 0
        while i < total:
            n = min(160, total - i)
            block = np.arange(i, i + n, dtype=np.float32)
            done = 0
            while done < n:  # retry what did not fit (no drops in this test)
                before = r.dropped
                done += r.write(block[done:])
                r.dropped = before
            i += n

    t = threading.Thread(target=produce)
    t.start()
    while sum(len(g) for g in got) < total:
        x = r.read(320)
        if x is None and r.available():
            x = r.read(min(r.available(), 320))
        if x is not None:
            got.append(x)
    t.join()
    seq = np.concatenate(got)[:total]
    np.testing.assert_array_equal(seq, np.arange(total, dtype=np.float32))


# -- simulated sound card ----------------------------------------------------------------


class FakeDuplex:
    """Calls ``callback`` every block on a real-time schedule (no drift), like PortAudio."""

    def __init__(
        self, *, samplerate: int, blocksize: int, device: Any, callback: Any, mic: np.ndarray
    ) -> None:
        self.rate, self.block, self.callback, self.mic = samplerate, blocksize, callback, mic
        self.played: list[np.ndarray] = []
        self.late_ms = 0.0
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        start, k = time.perf_counter(), 0
        while not self._stop.is_set() and (k + 1) * self.block <= len(self.mic):
            due = start + k * self.block / self.rate
            now = time.perf_counter()
            if due > now:
                time.sleep(due - now)
            else:
                self.late_ms = max(self.late_ms, (now - due) * 1000)
            indata = self.mic[k * self.block : (k + 1) * self.block].copy()
            outdata = np.zeros(self.block, np.float32)
            self.callback(indata, outdata, self.block, None)
            self.played.append(outdata)
            k += 1
        self._stop.set()

    def start(self) -> None:
        self._t.start()

    def stop(self) -> None:
        self._stop.set()
        self._t.join(5)

    def close(self) -> None:
        pass

    def wait(self) -> None:
        self._t.join()


def mic_signal(seconds: float) -> np.ndarray:
    s = speech(RATE)
    reps = int(np.ceil(seconds * RATE / len(s)))
    x = np.tile(s, reps)[: int(seconds * RATE)]
    return (x + 0.03 * pink(len(x))).astype(np.float32)


def run_live(seconds: float, **kw: Any) -> tuple[LiveSession, FakeDuplex]:
    mic = mic_signal(seconds)
    holder: dict[str, FakeDuplex] = {}

    def factory(**args: Any) -> FakeDuplex:
        holder["s"] = FakeDuplex(**args, mic=mic)
        return holder["s"]

    live = LiveSession(sample_rate=RATE, block_ms=10, stream_factory=factory, **kw)
    live.start()
    holder["s"].wait()
    live.stop()
    return live, holder["s"]


@pytest.mark.parametrize(
    "seconds", [10.0, pytest.param(60.0, marks=pytest.mark.slow)], ids=["10s", "60s"]
)
def test_realtime_monitor_has_no_dropouts(seconds: float) -> None:
    if seconds > 10 and not os.environ.get("NEXORA_SLOW_TESTS"):
        pytest.skip("set NEXORA_SLOW_TESTS=1 for the 60 s run")
    live, _ = run_live(seconds, monitor=True)
    st = live.stats
    assert st.blocks == int(seconds * 100)
    assert st.input_overflows == 0 and st.device_flags == 0
    # Linux: none at all. macOS VMs: their timer jitter can starve a 40 ms buffer a few
    # times even with 9 ms chunks (OPEN_ISSUES I-034), so allow up to 1% of blocks there
    allowed = 0 if sys.platform != "darwin" else st.blocks // 100
    assert st.output_underruns <= allowed, st
    # one slow chunk (another process taking the CPU) is absorbed by the 40 ms buffer; what
    # matters is no dropouts. Two buffers' worth would mean real trouble.
    assert st.worst_chunk_ms < 80
    assert {"speech_start"} <= set(st.events)


def test_monitor_plays_cleaned_audio() -> None:
    _, card = run_live(6.0, monitor=True)
    played = np.concatenate(card.played)
    mic = card.mic[: len(played)]

    # noise-only stretch: the fixture's speech has pauses; compare the quietest 10% of frames
    def floor_db(x: np.ndarray) -> float:
        fr = x[: len(x) // 320 * 320].reshape(-1, 320)
        e = np.sort(10 * np.log10(np.mean(fr**2, axis=1) + 1e-12))
        return float(np.mean(e[: len(e) // 10]))

    assert floor_db(played[RATE:]) < floor_db(mic[RATE:]) - 10  # noise removed in pauses


def test_agent_mode_plays_agent_audio_and_returns_clean_mic() -> None:
    mic = mic_signal(3.0)
    holder: dict[str, FakeDuplex] = {}

    def factory(**args: Any) -> FakeDuplex:
        holder["s"] = FakeDuplex(**args, mic=mic)
        return holder["s"]

    live = LiveSession(sample_rate=RATE, stream_factory=factory, monitor=False)
    tone = (0.2 * np.sin(2 * np.pi * 440 * np.arange(RATE) / RATE)).astype(np.float32)
    live.play(tone)
    live.start()
    chunks = []
    for c in live.processed_audio(timeout=0.2):
        chunks.append(c)
        if sum(len(x) for x in chunks) >= 2 * RATE:
            break
    holder["s"].wait()
    st = live.stop()
    played = np.concatenate(holder["s"].played)
    # the agent's tone was played after the 40 ms jitter buffer
    start = int(0.04 * RATE)
    np.testing.assert_allclose(played[start : start + RATE], tone, atol=1e-6)
    assert sum(len(x) for x in chunks) >= 2 * RATE
    assert st.input_overflows == 0


@pytest.mark.device
def test_real_sound_card_round_trip() -> None:
    """Run on your machine: ``pytest -m device``. Speak for 3 seconds."""
    try:
        import sounddevice as sd  # raises OSError, not ImportError, without PortAudio
    except (ImportError, OSError) as exc:
        pytest.skip(f"sounddevice unavailable: {exc}")
    try:
        sd.query_devices(kind="input")
    except Exception as exc:  # no PortAudio device here
        pytest.skip(str(exc))
    with LiveSession(monitor=True) as live:
        time.sleep(3)
    assert live.stats.dropouts() == 0, live.stats


def test_cli_process_and_help(tmp_path: Any) -> None:
    sf = pytest.importorskip("soundfile")
    from nexora_audio.cli import main

    x = mic_signal(2.0)
    src, dst = tmp_path / "in.wav", tmp_path / "out.wav"
    sf.write(src, x, RATE)
    assert main(["process", str(src), str(dst)]) == 0
    assert dst.stat().st_size > 1000
    with pytest.raises(SystemExit):
        main(["--help"])


def test_platform_wheel_hook_rejects_mixed_platforms(tmp_path: Any, monkeypatch: Any) -> None:
    import importlib.util
    from pathlib import Path

    pytest.importorskip("hatchling")

    root = Path(__file__).resolve().parents[2]
    if not (root / "hatch_build.py").exists():
        pytest.skip("not in the source tree (testing an installed wheel)")
    spec = importlib.util.spec_from_file_location("hatch_build", root / "hatch_build.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    native = tmp_path / "src" / "nexora_audio" / "_native"
    for d in ("linux-x86_64", "darwin-aarch64", "licenses"):
        (native / d).mkdir(parents=True)

    class Hook(mod.CustomBuildHook):  # type: ignore[name-defined,misc]
        def __init__(self) -> None:
            pass

        root = str(tmp_path)
        target_name = "wheel"

    monkeypatch.setenv("NEXORA_WHEEL_PLATFORM", "linux-x86_64")
    with pytest.raises(ValueError, match="only linux-x86_64"):
        Hook().initialize("0", {})
    (native / "darwin-aarch64").rmdir()
    data: dict[str, Any] = {}
    Hook().initialize("0", data)
    assert data["tag"] == "py3-none-manylinux_2_35_x86_64" and data["pure_python"] is False
