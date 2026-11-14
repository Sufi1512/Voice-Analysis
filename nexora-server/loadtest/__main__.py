"""Load / soak test: N simulated callers streaming real-time audio to /v1/stream.

    python -m loadtest --url http://127.0.0.1:8080 --key nx_... --sessions 8 --duration 60
    python -m loadtest ... --sessions 6 --duration 600 --call-seconds 60 --pid 12345   # soak

Each caller connects, waits for ``session.started``, sends 20 ms PCM16 chunks on a fixed
real-time schedule and reads the cleaned audio back. Measured: connect time, round trip per
chunk (send of chunk k to receipt of the output that completes it), rejections by close
code, errors, and (with ``--pid``) the server's memory every 5 s. With ``--call-seconds``
callers hang up and call again, as on a real line. Writes a JSON report.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import wave
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

RATE = 16000
CHUNK_MS = 20
CHUNK = RATE * CHUNK_MS // 1000
FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "nexora-audio"
    / "tests"
    / "fixtures"
    / "jfk_inaugural_16k.wav"
)


def audio_source() -> bytes:
    """Speech with pauses (looped), as PCM16 bytes."""
    if FIXTURE.exists():
        with wave.open(str(FIXTURE)) as w:
            x = np.frombuffer(w.readframes(w.getnframes()), np.int16)
    else:  # bursts of noise standing in for speech
        rng = np.random.default_rng(0)
        x = (rng.standard_normal(RATE * 10) * 3000).astype(np.int16)
        x[np.arange(len(x)) // RATE % 3 == 2] = 0
    pause = np.zeros(RATE, np.int16)
    return np.concatenate([x, pause]).tobytes()


@dataclass
class Stats:
    connect_ms: list[float] = field(default_factory=list)
    rtt_ms: list[float] = field(default_factory=list)
    late_send_ms: list[float] = field(default_factory=list)
    calls_ok: int = 0
    calls_failed: int = 0
    closes: Counter[str] = field(default_factory=Counter)
    errors: Counter[str] = field(default_factory=Counter)
    rss_mb: list[tuple[float, float]] = field(default_factory=list)
    events: Counter[str] = field(default_factory=Counter)


async def one_call(url: str, key: str, seconds: float, audio: bytes, st: Stats) -> None:
    import websockets

    t0 = time.perf_counter()
    try:
        ws = await websockets.connect(
            f"{url}/v1/stream?encoding=pcm16&sample_rate={RATE}",
            additional_headers={"Authorization": f"Bearer {key}"},
            open_timeout=20,
            max_size=2**22,
        )
    except Exception as exc:
        st.calls_failed += 1
        st.errors[f"connect:{type(exc).__name__}"] += 1
        return
    try:
        first = json.loads(await ws.recv())
        if first.get("type") != "session.started":
            st.calls_failed += 1
            st.closes[str(first.get("code"))] += 1
            return
        st.connect_ms.append((time.perf_counter() - t0) * 1000)
        nbytes = CHUNK * 2
        n_chunks = int(seconds * 1000 / CHUNK_MS)
        sent_at: list[float] = []
        received = 0
        done = asyncio.Event()

        async def reader() -> None:
            nonlocal received
            async for msg in ws:
                now = time.perf_counter()
                if isinstance(msg, bytes):
                    received += len(msg)
                    k = received // nbytes - 1  # last input chunk fully covered by output
                    if 0 <= k < len(sent_at):
                        st.rtt_ms.append((now - sent_at[k]) * 1000)
                else:
                    m = json.loads(msg)
                    st.events[m.get("type", "?")] += 1
                    if m.get("type") == "session.ended":
                        st.closes[str(m.get("close_code"))] += 1
            done.set()

        rd = asyncio.create_task(reader())
        start = time.perf_counter()
        off = 0
        for k in range(n_chunks):
            due = start + k * CHUNK_MS / 1000
            delay = due - time.perf_counter()
            if delay > 0:
                await asyncio.sleep(delay)
            else:
                st.late_send_ms.append(-delay * 1000)
            chunk = audio[off : off + nbytes]
            if len(chunk) < nbytes:
                off, chunk = 0, audio[:nbytes]
            off += nbytes
            sent_at.append(time.perf_counter())
            await ws.send(chunk)
        await ws.send(json.dumps({"type": "end"}))
        await asyncio.wait_for(done.wait(), 30)
        rd.cancel()
        st.calls_ok += 1
    except Exception as exc:
        st.calls_failed += 1
        st.errors[type(exc).__name__] += 1
    finally:
        await ws.close()


async def caller(url: str, key: str, until: float, call_s: float, audio: bytes, st: Stats) -> None:
    backoff = 0.25
    while time.perf_counter() < until:
        left = until - time.perf_counter()
        before = st.closes["1013"]
        await one_call(url, key, min(call_s, max(left, 1.0)), audio, st)
        if st.closes["1013"] > before:  # refused (full): back off like nexora_client does
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 4.0)
            continue
        backoff = 0.25


async def watch_rss(pid: int, until: float, st: Stats) -> None:
    t0 = time.perf_counter()
    while time.perf_counter() < until:
        try:
            for line in Path(f"/proc/{pid}/status").read_text().splitlines():
                if line.startswith("VmRSS:"):
                    st.rss_mb.append((time.perf_counter() - t0, int(line.split()[1]) / 1024))
        except OSError:
            return
        await asyncio.sleep(5)


def pct(xs: list[float], p: float) -> float | None:
    return round(float(np.percentile(xs, p)), 1) if xs else None


def summary(st: Stats, args: argparse.Namespace, wall: float) -> dict[str, Any]:
    rss = [m for _, m in st.rss_mb]
    return {
        "sessions": args.sessions,
        "duration_s": args.duration,
        "call_seconds": args.call_seconds,
        "wall_s": round(wall, 1),
        "calls_ok": st.calls_ok,
        "calls_failed": st.calls_failed,
        "close_codes": dict(st.closes),
        "errors": dict(st.errors),
        "connect_ms": {
            "p50": pct(st.connect_ms, 50),
            "p95": pct(st.connect_ms, 95),
            "max": pct(st.connect_ms, 100),
        },
        "round_trip_ms": {
            "p50": pct(st.rtt_ms, 50),
            "p95": pct(st.rtt_ms, 95),
            "p99": pct(st.rtt_ms, 99),
            "max": pct(st.rtt_ms, 100),
            "samples": len(st.rtt_ms),
        },
        "client_late_sends": len([x for x in st.late_send_ms if x > 10]),
        "events": dict(st.events),
        "server_rss_mb": {
            "first": rss[0] if rss else None,
            "last": rss[-1] if rss else None,
            "max": max(rss) if rss else None,
            "samples": st.rss_mb,
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser(prog="loadtest")
    ap.add_argument("--url", default="http://127.0.0.1:8080")
    ap.add_argument("--key", required=True)
    ap.add_argument("--sessions", type=int, default=8)
    ap.add_argument("--duration", type=float, default=60)
    ap.add_argument("--call-seconds", type=float, default=1e9, help="hang up and redial")
    ap.add_argument("--ramp", type=float, default=2.0, help="seconds to start all callers")
    ap.add_argument("--pid", type=int, default=0, help="server process id (memory)")
    ap.add_argument("--out", default="loadtest-report.json")
    args = ap.parse_args()
    url = args.url.replace("http://", "ws://").replace("https://", "wss://")
    audio = audio_source()
    st = Stats()

    async def run() -> float:
        t0 = time.perf_counter()
        until = t0 + args.duration + args.ramp
        tasks = []
        for _ in range(args.sessions):
            await asyncio.sleep(args.ramp / max(args.sessions, 1))
            tasks.append(
                asyncio.create_task(
                    caller(url, args.key, until, min(args.call_seconds, args.duration), audio, st)
                )
            )
        if args.pid:
            tasks.append(asyncio.create_task(watch_rss(args.pid, until + 5, st)))
        await asyncio.gather(*tasks)
        return time.perf_counter() - t0

    wall = asyncio.run(run())
    rep = summary(st, args, wall)
    Path(args.out).write_text(json.dumps(rep, indent=1))
    short = {k: v for k, v in rep.items() if k != "server_rss_mb"}
    short["server_rss_mb"] = {k: v for k, v in rep["server_rss_mb"].items() if k != "samples"}
    print(json.dumps(short, indent=1))


if __name__ == "__main__":
    main()
