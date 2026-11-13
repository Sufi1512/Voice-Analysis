"""Server capacity benchmark: CPU cost per StreamSession and parallel scaling.

Usage: python benchmarks/sessions.py [--seconds 20]
Prints a Markdown table. Processing time only (no network).
"""

from __future__ import annotations

import argparse
import concurrent.futures
import os
import platform
import time

import numpy as np

from nexora_audio import AudioFormat, StreamSession
from nexora_audio.streaming.codecs import encode

CONFIGS = {
    "DFN3 + enhancer + VAD/turns (default)": ({}, AudioFormat("pcm16", 16000)),
    "RNNoise + enhancer + VAD/turns": ({"noise_backend": "rnnoise"}, AudioFormat("pcm16", 16000)),
    "DFN3 default, telephony mu-law 8 kHz": ({}, AudioFormat("mulaw", 8000)),
    "DFN3 default, 48 kHz": ({}, AudioFormat("pcm16", 48000)),
}


def stream(fmt: AudioFormat, seconds: float) -> bytes:
    rng = np.random.default_rng(0)
    n = int(fmt.sample_rate * seconds)
    t = np.arange(n) / fmt.sample_rate
    x = 0.3 * np.sin(2 * np.pi * 180 * t) * (
        np.sin(2 * np.pi * 2 * t) > 0
    ) + 0.05 * rng.standard_normal(n)
    return encode(x.astype(np.float32)[None, :], fmt)


def one_session(settings: dict, fmt: AudioFormat, data: bytes) -> tuple[float, float, float]:
    step = fmt.bytes_for_ms(20)
    with StreamSession(input_format=fmt, **settings) as s:
        t0 = time.process_time()
        w0 = time.perf_counter()
        for i in range(0, len(data), step):
            s.process(data[i : i + step])
        return time.process_time() - t0, time.perf_counter() - w0, s.timing.p99_ms


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=20.0)
    args = ap.parse_args()
    cores = os.cpu_count() or 1
    print(
        f"Machine: {platform.processor() or platform.machine()}, {cores} logical CPUs, "
        f"Python {platform.python_version()}, {args.seconds:.0f} s of audio per session, "
        "20 ms chunks\n"
    )
    print(
        "| Pipeline | CPU per audio second | Sessions per core (real-time) | p99 per 20 ms chunk | "
        f"{cores} sessions in parallel: wall RTF |"
    )
    print("|---|---|---|---|---|")
    for name, (settings, fmt) in CONFIGS.items():
        data = stream(fmt, args.seconds)
        one_session(settings, fmt, stream(fmt, 1.0))  # warm-up
        cpu, _, p99 = one_session(settings, fmt, data)
        rtf = cpu / args.seconds
        with concurrent.futures.ThreadPoolExecutor(cores) as ex:
            w0 = time.perf_counter()
            futures = [ex.submit(one_session, settings, fmt, data) for _ in range(cores)]
            for f in futures:
                f.result()
            par_rtf = (time.perf_counter() - w0) / args.seconds
        print(f"| {name} | {rtf * 1000:.0f} ms | {1 / rtf:.1f} | {p99:.2f} ms | {par_rtf:.3f} |")


if __name__ == "__main__":
    main()
