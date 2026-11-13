"""Evaluate quality gates over result rows, and compare with a stored baseline."""

from __future__ import annotations

import operator
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

GATES_FILE = Path(__file__).with_name("gates.toml")
_OPS = {"<=": operator.le, ">=": operator.ge}


@dataclass
class GateResult:
    id: str
    title: str
    phase: str
    enforce: bool
    op: str
    threshold: float
    value: float | None
    rows: int
    passed: bool | None  # None: no data in this profile
    baseline: float | None = None
    regressed: bool = False

    @property
    def status(self) -> str:
        if self.passed is None:
            return "no data"
        if self.regressed:
            return "REGRESSED"
        if self.passed:
            return "pass"
        return "FAIL" if self.enforce else f"target ({self.phase})"


def load(path: Path = GATES_FILE) -> list[dict[str, Any]]:
    with path.open("rb") as f:
        return list(tomllib.load(f)["gate"])


def _select(rows: list[dict[str, Any]], g: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        if "error" in r or r["set"] not in g["sets"]:
            continue
        snr = r.get("snr")
        if "min_snr" in g and snr is not None and snr < g["min_snr"]:
            continue
        if "max_snr" in g and (snr is None or snr > g["max_snr"]):
            continue
        if "kind" in g and r.get("kind") != g["kind"]:
            continue
        if "loss_pct" in g and r.get("loss_pct") != g["loss_pct"]:
            continue
        out.append(r)
    return out


def _value(rows: list[dict[str, Any]], g: dict[str, Any]) -> tuple[float | None, int]:
    agg = g["agg"]
    if agg in ("wer_delta", "wer_reduction"):
        rows = [r for r in rows if "words" in r]
        words = sum(r["words"] for r in rows)
        if not words:
            return None, 0
        w_in = 100 * sum(r["errors_in"] for r in rows) / words
        w_out = 100 * sum(r["errors_out"] for r in rows) / words
        if agg == "wer_delta":
            return w_out - w_in, len(rows)
        return (100 * (w_in - w_out) / w_in if w_in else 0.0), len(rows)
    if agg == "pause_pct":
        total = sum(r.get("pauses", 0) for r in rows)
        return (100 * sum(r[g["metric"]] for r in rows) / total if total else None), len(rows)
    vals = [r[g["metric"]] for r in rows if r.get(g["metric"]) is not None]
    if not vals:
        return None, 0
    a = np.asarray(vals, dtype=float)
    fn = {"max": np.max, "min": np.min, "mean": np.mean, "median": np.median, "sum": np.sum}
    if agg == "pct_true":
        return float(100 * a.mean()), len(vals)
    return float(fn[agg](a)), len(vals)


def evaluate(
    rows: list[dict[str, Any]],
    baseline: dict[str, float] | None = None,
    gates: list[dict[str, Any]] | None = None,
) -> list[GateResult]:
    results = []
    for g in gates or load():
        value, n = _value(_select(rows, g), g)
        passed = None if value is None else bool(_OPS[g["op"]](value, g["threshold"]))
        res = GateResult(
            g["id"],
            g["title"],
            g.get("phase", ""),
            bool(g.get("enforce", False)),
            g["op"],
            float(g["threshold"]),
            value,
            n,
            passed,
        )
        if (
            baseline
            and g.get("regress", True)
            and value is not None
            and baseline.get(g["id"]) is not None
        ):
            res.baseline = baseline[g["id"]]
            tol = float(g.get("tolerance", 0))
            worse = value - res.baseline if g["op"] == "<=" else res.baseline - value
            res.regressed = worse > tol + 1e-9
        results.append(res)
    return results


def failed(results: list[GateResult]) -> list[GateResult]:
    return [r for r in results if r.regressed or (r.enforce and r.passed is False)]
