"""Markdown report from result rows and gate results."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np

from qualitylab.gates import GateResult


def _fmt(v: float | None, digits: int = 2) -> str:
    return "-" if v is None else f"{v:.{digits}f}"


def _stat(rows: list[dict[str, Any]], key: str, fn: Any) -> float | None:
    vals = [r[key] for r in rows if r.get(key) is not None]
    return float(fn(vals)) if vals else None


def _wer(rows: list[dict[str, Any]], key: str) -> float | None:
    words = sum(r.get("words", 0) for r in rows)
    return 100 * sum(r.get(key, 0) for r in rows) / words if words else None


def render(rows: list[dict[str, Any]], gates: list[GateResult], meta: dict[str, Any]) -> str:
    lines = [
        f"# Voice quality report: {meta['profile']} profile",
        "",
        f"Generated {meta['date']} by `python -m qualitylab run --profile {meta['profile']}`. "
        f"{len(rows)} cases, {meta['audio_minutes']:.1f} minutes of audio, "
        f"run time {meta['run_minutes']:.1f} minutes. Pipeline settings: "
        f"`{meta['settings'] or 'product defaults'}`; backends: {meta['backends']}. "
        f"STT: {meta['stt']}.",
        "",
        "## Gates",
        "",
        "| Gate | Phase | Target | Value | Baseline | Status |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for g in gates:
        lines.append(
            f"| {g.title} | {g.phase} | {g.op} {g.threshold:g} | {_fmt(g.value)} | "
            f"{_fmt(g.baseline)} | {g.status} |"
        )
    errors = [r for r in rows if "error" in r]
    if errors:
        lines += ["", f"**{len(errors)} cases failed to run:**", ""]
        lines += [f"- `{r['id']}`: {r['error']}" for r in errors]

    by_set: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        if "error" not in r:
            by_set[r["set"]].append(r)
    speech_sets = [s for s in ("clean", "noise", "phone", "reverb", "loss") if s in by_set]
    lines += [
        "",
        "## Speech sets",
        "",
        "| Set | Cases | STOI in → out | SI-SDR in → out (dB) | Speech cut max (%) | "
        "Pause noise median (dB) | Under voice median (dB) | WER in → out (%) |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for s in speech_sets:
        rs = by_set[s]
        lines.append(
            f"| {s} | {len(rs)} | {_fmt(_stat(rs, 'stoi_in', np.mean), 3)} → "
            f"{_fmt(_stat(rs, 'stoi_out', np.mean), 3)} | "
            f"{_fmt(_stat(rs, 'si_sdr_in', np.mean), 1)}"
            f" → {_fmt(_stat(rs, 'si_sdr_out', np.mean), 1)} | "
            f"{_fmt(_stat(rs, 'speech_cut_pct', np.max), 1)} | "
            f"{_fmt(_stat(rs, 'pause_noise_db', np.median), 1)} | "
            f"{_fmt(_stat(rs, 'under_voice_db', np.median), 1)} | "
            f"{_fmt(_wer(rs, 'errors_in'), 1)} → {_fmt(_wer(rs, 'errors_out'), 1)} |"
        )

    noise_rows = by_set.get("noise", [])
    if noise_rows:
        lines += [
            "",
            "## Noise set by noise type",
            "",
            "| Noise | Cases | STOI Δ mean | Speech cut max (%) | Pause noise worst (dB) | "
            "Under voice median (dB) | Pumping max (dB) | WER in → out (%) |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in noise_rows:
            groups[r["noise"]].append(r)
        for name, rs in sorted(groups.items()):
            lines.append(
                f"| {name} | {len(rs)} | {_fmt(_stat(rs, 'stoi_delta', np.mean), 3)} | "
                f"{_fmt(_stat(rs, 'speech_cut_pct', np.max), 1)} | "
                f"{_fmt(_stat(rs, 'pause_noise_db', np.max), 1)} | "
                f"{_fmt(_stat(rs, 'under_voice_db', np.median), 1)} | "
                f"{_fmt(_stat(rs, 'pumping_db', np.max), 1)} | "
                f"{_fmt(_wer(rs, 'errors_in'), 1)} → {_fmt(_wer(rs, 'errors_out'), 1)} |"
            )
        snr_groups: dict[float, list[dict[str, Any]]] = defaultdict(list)
        for r in noise_rows:
            snr_groups[r["snr"]].append(r)
        lines += [
            "",
            "## Noise set by SNR",
            "",
            "| SNR (dB) | Cases | STOI in → out | Speech cut max (%) | WER in → out (%) |",
            "| --- | --- | --- | --- | --- |",
        ]
        for snr, rs in sorted(snr_groups.items()):
            lines.append(
                f"| {snr:g} | {len(rs)} | {_fmt(_stat(rs, 'stoi_in', np.mean), 3)} → "
                f"{_fmt(_stat(rs, 'stoi_out', np.mean), 3)} | "
                f"{_fmt(_stat(rs, 'speech_cut_pct', np.max), 1)} | "
                f"{_fmt(_wer(rs, 'errors_in'), 1)} → {_fmt(_wer(rs, 'errors_out'), 1)} |"
            )

    for name, cols in (
        (
            "echo",
            [
                "kind",
                "delay_ms",
                "echo_db",
                "erle_db",
                "false_barge_ins",
                "missed_barge_in",
                "double_talk_cut_pct",
                "double_talk_stoi",
            ],
        ),
        ("turns", ["pauses_ms", "pauses", "pauses_cut", "reply_gap_ms"]),
        (
            "turns_tts",
            ["lang", "kind", "variant", "line", "pauses_ms", "pauses_cut", "reply_gap_ms"],
        ),
        ("loss", ["loss_pct", "lost_fraction", "stoi_out", "loss_stoi_drop"]),
    ):
        rs = by_set.get(name, [])
        if not rs:
            continue
        lines += [
            "",
            f"## {name.capitalize()} set",
            "",
            "| Case | " + " | ".join(cols) + " |",
            "| --- | " + " | ".join("---" for _ in cols) + " |",
        ]
        for r in rs:
            vals = []
            for c in cols:
                v = r.get(c)
                vals.append(f"{v:.3g}" if isinstance(v, float) else ("-" if v is None else str(v)))
            lines.append(f"| `{r['id']}` | " + " | ".join(vals) + " |")
    lines.append("")
    return "\n".join(lines)
