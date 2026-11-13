"""Run the nexora-audio pipeline over corpus cases and measure each one."""

from __future__ import annotations

import time
import zlib
from typing import Any

import numpy as np

from nexora_audio.streaming.codecs import AudioFormat, StreamDecoder, encode
from nexora_audio.streaming.session import StreamSession
from qualitylab import metrics as m
from qualitylab.corpus import Case

CHUNK_MS = 20


def process(case: Case, settings: dict[str, Any]) -> dict[str, Any]:
    """Stream the case through a StreamSession in 20 ms chunks, as a live call would."""
    fmt = AudioFormat(encoding=case.encoding, sample_rate=case.rate)  # type: ignore[arg-type]
    wire = encode(case.mic[None, :], fmt)
    step = fmt.bytes_for_ms(CHUNK_MS)
    chunk_s = CHUNK_MS / 1000
    out = bytearray()
    events: list[dict[str, Any]] = []
    times: list[float] = []
    with StreamSession(input_format=fmt, **settings) as sess:
        latency_ms = sess.latency_ms
        speaking = False
        for k, i in enumerate(range(0, len(wire), step)):
            t = k * chunk_s
            now = any(s <= t < e for s, e in case.agent_spans)
            if now != speaking:
                sess.set_agent_speaking(now)
                speaking = now
            t0 = time.perf_counter()
            res = sess.process(wire[i : i + step])
            times.append(time.perf_counter() - t0)
            out += res.audio
            events += [ev.to_dict() for ev in res.events]
        res = sess.flush()
        out += res.audio
        events += [ev.to_dict() for ev in res.events]
        backends = sess.backends
    y = StreamDecoder(fmt).decode(bytes(out))[0]
    return {
        "out": y,
        "events": events,
        "latency_ms": latency_ms,
        "chunk_p99_ms": float(np.percentile(times, 99) * 1000),
        "backends": backends,
    }


_STT_MEMO: dict[int, str] = {}


def _transcribe_memo(x: np.ndarray, rate: int) -> str:
    from qualitylab import stt

    key = zlib.crc32(x.tobytes()) ^ rate
    if key not in _STT_MEMO:
        _STT_MEMO[key] = stt.transcribe(x, rate)
    return _STT_MEMO[key]


def measure(case: Case, settings: dict[str, Any], use_stt: bool) -> dict[str, Any]:
    r = process(case, settings)
    rate = case.rate
    n = len(case.mic)
    delay = round(r["latency_ms"] * rate / 1000)
    out = m.align(r["out"], delay, n)
    row: dict[str, Any] = {
        "id": case.id,
        "set": case.set,
        **case.meta,
        "seconds": round(case.seconds, 2),
        "latency_ms": round(r["latency_ms"], 2),
        "chunk_p99_ms": round(r["chunk_p99_ms"], 3),
        "backends": r["backends"],
    }
    ev = r["events"]
    lat_s = r["latency_ms"] / 1000

    if case.set in ("clean", "noise", "phone", "reverb", "loss", "turns"):
        s0, s1 = case.speech_span
        sp = slice(int(max(0, s0 - 0.2) * rate), int(min(n / rate, s1 + 0.3) * rate))
        row["stoi_in"] = round(m.stoi(case.clean[sp], case.mic[sp], rate), 4)
        row["stoi_out"] = round(m.stoi(case.clean[sp], out[sp], rate), 4)
        row["stoi_delta"] = round(row["stoi_out"] - row["stoi_in"], 4)
        row["si_sdr_in"] = round(m.si_sdr(case.clean[sp], case.mic[sp]), 2)
        row["si_sdr_out"] = round(m.si_sdr(case.clean[sp], out[sp]), 2)
        row["speech_cut_pct"] = round(m.speech_cut_pct(case.clean, case.noise, out, rate), 2)
        if case.noise is not None and np.any(case.noise) and case.set != "turns":
            row["pause_noise_db"] = round(
                m.pause_noise_db(case.noise, out, rate, case.speech_span), 1
            )
            row["pause_level_dbfs"] = round(m.pause_level_dbfs(out, rate, case.speech_span), 1)
            row["under_voice_db"] = round(m.under_voice_db(case.clean, case.noise, out, rate), 1)
            row["pumping_db"] = round(m.pumping_db(out, rate, case.speech_span), 2)
        if case.set == "clean":
            est = m.estimate_delay(case.clean, r["out"], int(0.2 * rate))
            row["latency_measured_ms"] = round(est * 1000 / rate, 2)
            row["latency_error_ms"] = round(abs(row["latency_measured_ms"] - r["latency_ms"]), 2)
        if use_stt and case.stt:
            ref = _transcribe_memo(case.clean, rate)
            hyp_in = _transcribe_memo(case.mic, rate)
            hyp_out = _transcribe_memo(out, rate)
            e_in, words = m.word_errors(ref, hyp_in)
            e_out, _ = m.word_errors(ref, hyp_out)
            row.update(
                words=words,
                errors_in=e_in,
                errors_out=e_out,
                wer_in=round(100 * e_in / max(words, 1), 2),
                wer_out=round(100 * e_out / max(words, 1), 2),
            )

    if case.set == "echo":
        interruptions = [e for e in ev if e["type"] == "interruption"]
        a0, a1 = case.agent_spans[0]
        if case.meta["kind"] == "single":
            mask = m.region(n, rate, [(a0 + 0.3, a1)])
            row["erle_db"] = round(m.erle_db(case.mic, out, mask), 1)
            row["false_barge_ins"] = len(interruptions)
        else:
            s0, s1 = case.speech_span
            hit = [e for e in interruptions if s0 <= e["time_ms"] / 1000 - lat_s <= s0 + 1.5]
            early = [e for e in interruptions if e["time_ms"] / 1000 - lat_s < s0]
            row["missed_barge_in"] = int(not hit)
            row["false_barge_ins"] = len(early)
            nz = (case.echo if case.echo is not None else 0) + (
                case.noise if case.noise is not None else 0
            )
            row["double_talk_cut_pct"] = round(m.speech_cut_pct(case.clean, nz, out, rate), 2)
            sp = slice(int(s0 * rate), int(min(s1, a1) * rate))
            if sp.stop - sp.start > rate:
                row["double_talk_stoi"] = round(m.stoi(case.clean[sp], out[sp], rate), 4)

    if case.set == "turns":
        eot = [e["time_ms"] / 1000 - lat_s for e in ev if e["type"] == "end_of_turn"]
        pauses = case.labels["pauses"]
        cut = [any(s <= t <= e + 0.2 for t in eot) for s, e in pauses]
        row["pauses"] = len(pauses)
        row["pauses_cut"] = int(sum(cut))
        after = [t for t in eot if t >= case.labels["true_end"]]
        row["reply_gap_ms"] = (
            round((after[0] - case.labels["true_end"]) * 1000, 1) if after else None
        )
    return row


def run_case(args: tuple[Case, dict[str, Any], bool]) -> dict[str, Any]:
    case, settings, use_stt = args
    try:
        return measure(case, settings, use_stt)
    except Exception as exc:  # report, never hide, a broken case
        return {"id": case.id, "set": case.set, **case.meta, "error": repr(exc)}


def add_pairs(rows: list[dict[str, Any]]) -> None:
    """Loss cases: STOI drop against the same audio without loss."""
    by_id = {r["id"]: r for r in rows}
    for r in rows:
        twin = by_id.get(r.get("pair", ""))
        if r.get("loss_pct") and twin and "stoi_out" in r and "stoi_out" in twin:
            r["loss_stoi_drop"] = round(twin["stoi_out"] - r["stoi_out"], 4)
