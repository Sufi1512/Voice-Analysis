"""E11 research spike: speaker gate for background voices (go/no-go measurement).

Idea: learn the caller's voice from their first ~3 s of speech (3D-Speaker ERes2Net
embeddings, Apache-2.0), then every 0.25 s compare the last 1.5 s of speech with it; when
someone else is talking, mute the output (-30 dB) until the caller is back. Runs causally on
the output of today's full pipeline (StreamSession defaults), so it measures what the gate
adds. It cannot separate voices that overlap: that needs a target-speaker extraction model.

Run:  NEXORA_QL_CACHE=qualitylab/.cache PYTHONPATH=src:. python spikes/e11_speaker_gate.py
Needs the files listed in docs/E11_REPORT.md under qualitylab/.cache/e11 and .../tts.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import sherpa_onnx as so
from scipy.io import wavfile

from nexora_audio import StreamSession
from nexora_audio.streaming.codecs import AudioFormat
from qualitylab import sources, synth
from qualitylab.corpus import _level

RATE = 16000
HOP = RATE // 4  # decision every 0.25 s
WIN = int(1.5 * RATE)  # embedding window
FRAME = RATE // 50  # 20 ms
THRESHOLD = 0.35  # between same-speaker p10 (0.45) and different-speaker p90 (0.25), set before testing
MUTE_DB = -30.0
E11 = Path("qualitylab/.cache/e11")


class Embedder:
    def __init__(self, model: str) -> None:
        self.ex = so.SpeakerEmbeddingExtractor(
            so.SpeakerEmbeddingExtractorConfig(model=str(E11 / model), num_threads=1)
        )
        self.calls, self.seconds = 0, 0.0

    def __call__(self, x: np.ndarray) -> np.ndarray:
        t = time.perf_counter()
        s = self.ex.create_stream()
        s.accept_waveform(RATE, x.astype(np.float32))
        s.input_finished()
        e = np.asarray(self.ex.compute(s), np.float32)
        self.calls += 1
        self.seconds += time.perf_counter() - t
        return e / (np.linalg.norm(e) + 1e-9)


def frame_db(x: np.ndarray) -> np.ndarray:
    fr = x[: len(x) // FRAME * FRAME].reshape(-1, FRAME)
    return 10 * np.log10(np.mean(fr.astype(np.float64) ** 2, axis=1) + 1e-12)


@dataclass
class GateStats:
    enrolled_at_s: float | None = None
    muted_hops: int = 0


def speaker_gate(y: np.ndarray, emb: Embedder) -> tuple[np.ndarray, GateStats]:
    """Causal: the decision made at time t applies to the audio after t."""
    st = GateStats()
    db = frame_db(y)
    floor = np.percentile(db, 10)
    active = db > floor + 12  # speech present (after noise removal)
    gain = np.ones(len(y), np.float32)
    profile: np.ndarray | None = None
    enroll: list[np.ndarray] = []
    other_run, muted = 0, False
    mute = 10 ** (MUTE_DB / 20)
    for start in range(WIN, len(y) - HOP + 1, HOP):
        f0, f1 = (start - WIN) // FRAME, start // FRAME
        frac = float(np.mean(active[f0:f1]))
        if frac >= 0.5:
            e = emb(y[start - WIN : start])
            if profile is None:
                if frac >= 0.6:
                    enroll.append(e)
                    if len(enroll) == 6:  # ~3 s of the first speaker (the caller speaks first)
                        p = np.mean(enroll, axis=0)
                        profile = p / np.linalg.norm(p)
                        st.enrolled_at_s = start / RATE
            else:
                sim = float(e @ profile)
                if sim < THRESHOLD:
                    other_run += 1
                    if other_run >= 2:
                        muted = True
                else:
                    other_run, muted = 0, False
                    if sim > 0.55:  # follow slow changes in the caller's voice
                        p = 0.95 * profile + 0.05 * e
                        profile = p / np.linalg.norm(p)
        if muted:
            gain[start : start + HOP] = mute
            st.muted_hops += 1
    # 20 ms ramps at gain changes (no clicks)
    k = np.ones(FRAME, np.float32) / FRAME
    gain = np.convolve(gain, k, mode="same").astype(np.float32)
    return y * gain, st


def run_pipeline(x: np.ndarray) -> np.ndarray:
    fmt = AudioFormat("float32", RATE)
    out = bytearray()
    with StreamSession(input_format=fmt) as s:
        lat = round(s.latency_ms * RATE / 1000)
        for i in range(0, len(x), FRAME):
            out += s.process(x[i : i + FRAME].astype(np.float32).tobytes()).audio
        out += s.flush().audio
    y = np.frombuffer(bytes(out), np.float32)
    y = y[lat : lat + len(x)]
    return np.pad(y, (0, len(x) - len(y)))


def voices() -> dict[str, np.ndarray]:
    out = {}
    for f in sorted((E11 / "voices").glob("*.wav")):
        _, a = wavfile.read(f)
        out[f"tts:{f.stem}"] = a.astype(np.float32) / 32768
    for name, x in sources.speech_clips().items():
        out[f"real:{name}"] = x
    return out


def pick_pairs(v: dict[str, np.ndarray], check: Embedder) -> list[tuple[str, str]]:
    """Different speakers, judged by a *different* model (WeSpeaker) than the gate uses."""
    real = sorted((k for k in v if k.startswith("real:")), key=lambda k: int(k[10:]))
    pairs: list[tuple[str, str]] = []
    for i, a in enumerate(real):
        b = real[(i + 7) % len(real)]
        if check(v[a][: 2 * WIN]) @ check(v[b][: 2 * WIN]) < 0.45:
            pairs.append((a, b))
        if len(pairs) == 6:
            break
    pairs += [("tts:lessac", "tts:ryan"), ("tts:alan", "tts:lessac"), ("tts:ryan", "tts:alan")]
    pairs += [(real[0], "tts:ryan"), ("tts:lessac", real[5])]
    return pairs


def segments(x: np.ndarray, lengths_s: list[float], offset_s: float) -> list[np.ndarray]:
    out, pos = [], int(offset_s * RATE) % max(len(x) - 1, 1)
    for L in lengths_s:
        n = int(L * RATE)
        seg = np.resize(np.roll(x, -pos), n)
        out.append(seg)
        pos += n
    return out


def build(a: np.ndarray, b: np.ndarray, scenario: str, rel_db: float, seed: int) -> dict:
    a, b = _level(a), _level(b) * 10 ** (rel_db / 20)
    lead = np.zeros(RATE, np.float32)
    if scenario == "pause":
        ca = segments(a, [4, 3, 2.5], 0.5)
        cb = segments(b, [3, 3], 1.0)
        parts_a = [lead, ca[0], np.zeros(len(cb[0])), ca[1], np.zeros(len(cb[1])), ca[2]]
        parts_b = [lead, np.zeros(len(ca[0])), cb[0], np.zeros(len(ca[1])), cb[1], np.zeros(len(ca[2]))]
        A, B = np.concatenate(parts_a), np.concatenate(parts_b)
    elif scenario == "overlap":
        A = np.concatenate([lead, segments(a, [12], 0.5)[0]])
        B = np.concatenate([lead, np.zeros(3 * RATE), segments(b, [9], 1.0)[0]])  # TV from 4 s
    else:  # solo
        A = np.concatenate([lead, segments(a, [12], 0.5)[0]])
        B = np.zeros_like(A)
    A = np.concatenate([A, np.zeros(RATE)]).astype(np.float32)
    B = np.concatenate([B, np.zeros(RATE)]).astype(np.float32)
    rng_noise = synth.pink(len(A), seed) if hasattr(synth, "pink") else np.random.default_rng(seed).standard_normal(len(A))
    noise = synth.scale_to_snr(A + 1e-9, rng_noise.astype(np.float32), 30)
    return {"A": A, "B": B, "mix": (A + B + noise).astype(np.float32)}


def metrics(case: dict, base: np.ndarray, gated: np.ndarray) -> dict:
    da, dbb = frame_db(case["A"]), frame_db(case["B"])
    caller = da > da.max() - 30
    bg_only = (dbb > dbb.max() - 30) & ~caller if dbb.max() > -100 else np.zeros_like(caller)
    n = min(len(caller), len(frame_db(base)))
    caller, bg_only = caller[:n], bg_only[:n]

    def energy(x: np.ndarray, mask: np.ndarray) -> float:
        fr = x[: n * FRAME].reshape(-1, FRAME)
        return float(np.sum(fr[mask] ** 2)) + 1e-12

    out: dict = {}
    if bg_only.any():
        e_in = energy(case["B"], bg_only)
        out["bg_left_base_db"] = round(10 * np.log10(energy(base, bg_only) / e_in), 1)
        out["bg_left_gate_db"] = round(10 * np.log10(energy(gated, bg_only) / e_in), 1)
    # caller frames the gate cut (>10 dB below the pipeline's own output)
    gb, gg = frame_db(base)[:n], frame_db(gated)[:n]
    out["caller_cut_pct"] = round(100 * float(np.mean((gg < gb - 10)[caller])), 1)
    return out


def main() -> None:
    gate_emb = Embedder("3dspeaker_speech_eres2net_sv_en_voxceleb_16k.onnx")
    check_emb = Embedder("wespeaker_en_voxceleb_resnet34.onnx")
    v = voices()
    pairs = pick_pairs(v, check_emb)
    rows = []
    t0 = time.time()
    for k, (ca, bg) in enumerate(pairs):
        for scenario, rel in (("pause", 0.0), ("pause", -6.0), ("overlap", -6.0), ("solo", 0.0)):
            case = build(v[ca], v[bg], scenario, rel, seed=k)
            base = run_pipeline(case["mix"])
            gated, st = speaker_gate(base, gate_emb)
            m = metrics(case, base, gated)
            row = {"caller": ca, "background": bg, "scenario": scenario, "rel_db": rel,
                   "enrolled_at_s": st.enrolled_at_s, **m}
            rows.append(row)
            print(json.dumps(row), flush=True)
    audio_s = sum(len(build(v[a], v[b], s, r, 0)["mix"]) for a, b in pairs[:1] for s, r in (("pause", 0),)) / RATE
    cost = {"embedding_ms_per_call": round(1000 * gate_emb.seconds / max(gate_emb.calls, 1), 1),
            "embeddings": gate_emb.calls, "wall_s": round(time.time() - t0, 1), "example_case_s": audio_s}
    Path("/tmp/e11_results.json").write_text(json.dumps({"rows": rows, "cost": cost}, indent=1))
    print(json.dumps(cost))


if __name__ == "__main__":
    sys.exit(main())
