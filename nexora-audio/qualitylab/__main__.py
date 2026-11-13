"""CLI: ``python -m qualitylab fetch|run``."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import multiprocessing as mp
import sys
import time
from pathlib import Path
from typing import Any

from qualitylab import corpus, gates, report, runner, sources, stt

BASELINE = Path(__file__).with_name("baseline.json")


def _parse_settings(items: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for item in items:
        key, _, raw = item.partition("=")
        out[key] = json.loads(raw) if raw[:1] in "0123456789-[{tf" or raw == "null" else raw
    return out


def cmd_fetch(args: argparse.Namespace) -> int:
    print("MS-SNSD test audio ->", sources.fetch_mssnsd())
    if args.stt:
        print("Whisper tiny.en (sherpa-onnx) ->", sources.fetch_stt())
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    settings = _parse_settings(args.set or [])
    use_stt = not args.no_stt and stt.available()
    cases = list(corpus.build(args.profile))
    if args.only:
        cases = [c for c in cases if c.set in args.only.split(",")]
    if args.match:
        cases = [c for c in cases if any(m in c.id for m in args.match.split(","))]
    print(
        f"{len(cases)} cases, {sum(c.seconds for c in cases) / 60:.1f} min audio, "
        f"STT {'on' if use_stt else 'off'}",
        flush=True,
    )
    t0 = time.time()
    jobs = [(c, settings, use_stt) for c in cases]
    with mp.get_context("fork").Pool(args.workers) as pool:
        rows = []
        for i, row in enumerate(pool.imap(runner.run_case, jobs), 1):
            rows.append(row)
            if i % 10 == 0 or i == len(jobs):
                print(f"  {i}/{len(jobs)} ({time.time() - t0:.0f} s)", flush=True)
    runner.add_pairs(rows)

    baseline = None
    if not args.no_baseline and BASELINE.exists():
        baseline = json.loads(BASELINE.read_text()).get(args.profile)
    results = gates.evaluate(rows, baseline)
    meta = {
        "profile": args.profile,
        "date": dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "audio_minutes": sum(c.seconds for c in cases) / 60,
        "run_minutes": (time.time() - t0) / 60,
        "settings": settings,
        "backends": sorted({b for r in rows for b in r.get("backends", [])}),
        "stt": "Whisper tiny.en int8 via sherpa-onnx" if use_stt else "off",
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    clean_rows = [{k: v for k, v in r.items() if k != "backends"} for r in rows]
    (out / f"results-{args.profile}.json").write_text(
        json.dumps({"meta": meta, "rows": clean_rows}, indent=1, default=str)
    )
    md = report.render(rows, results, meta)
    (out / f"report-{args.profile}.md").write_text(md)
    for g in results:
        print(
            f"  {g.status:>14}  {g.id:<18} {g.value if g.value is None else round(g.value, 3)}"
            f" ({g.op} {g.threshold:g})"
        )
    if args.write_baseline:
        data = json.loads(BASELINE.read_text()) if BASELINE.exists() else {}
        data[args.profile] = {g.id: g.value for g in results if g.value is not None}
        BASELINE.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")
        print("baseline written:", BASELINE)
    errors = [r for r in rows if "error" in r]
    bad = gates.failed(results)
    if errors:
        print(f"{len(errors)} cases failed to run", file=sys.stderr)
    if bad:
        print("FAILED gates: " + ", ".join(g.id for g in bad), file=sys.stderr)
    return 1 if (bad or errors) else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m qualitylab")
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch", help="download pinned public test audio (and the STT model)")
    f.add_argument("--stt", action="store_true", help="also fetch the Whisper tiny.en model")
    r = sub.add_parser("run", help="run the corpus and check the gates")
    r.add_argument("--profile", choices=["fast", "full"], default="fast")
    r.add_argument("--out", default="qualitylab/out")
    r.add_argument("--workers", type=int, default=max(1, mp.cpu_count()))
    r.add_argument("--only", help="comma-separated sets, e.g. echo,turns")
    r.add_argument("--match", help="comma-separated substrings of case ids, e.g. babble,phone/")
    r.add_argument(
        "--set",
        action="append",
        metavar="KEY=VALUE",
        help="pipeline setting override, e.g. noise_backend=rnnoise",
    )
    r.add_argument("--no-stt", action="store_true")
    r.add_argument("--no-baseline", action="store_true", help="skip the regression check")
    r.add_argument(
        "--write-baseline",
        action="store_true",
        help="store this run's gate values as the new baseline",
    )
    args = p.parse_args(argv)
    return cmd_fetch(args) if args.cmd == "fetch" else cmd_run(args)


if __name__ == "__main__":
    raise SystemExit(main())
