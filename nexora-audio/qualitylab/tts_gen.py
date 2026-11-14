"""Generate the synthetic turn-taking set with offline TTS (Piper voices via sherpa-onnx).

Run in a separate environment that has ``sherpa-onnx==1.12.40`` (2.x dropped the espeak
front end these voices need), numpy and scipy:

    python -I qualitylab/tts_gen.py qualitylab/.cache/tts

Reads the voices from ``<dir>/vits-piper-en_US-lessac-medium`` and
``<dir>/vits-piper-ar_JO-kareem-medium`` (see ``SOURCES.md``) and writes
``<dir>/turns/<id>.wav`` (16 kHz, 16-bit) plus ``<dir>/turns/labels.json``: for each case
the sample where the pause goes, the text up to it and the full text. The corpus inserts
the pauses and the noise. Output stays in the git-ignored cache: the voices' licences
allow research use, so nothing generated is committed or shipped.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import sherpa_onnx as so
from scipy.io import wavfile
from scipy.signal import resample_poly

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tts_scripts  # runs outside the package, in the TTS environment

RATE = 16000
VOICES = {"en": "vits-piper-en_US-lessac-medium", "ar": "vits-piper-ar_JO-kareem-medium"}
HOP = 160  # 10 ms


def voice(root: Path, name: str) -> so.OfflineTts:
    d = root / name
    model = next(d.glob("*.onnx"))
    cfg = so.OfflineTtsConfig(
        model=so.OfflineTtsModelConfig(
            vits=so.OfflineTtsVitsModelConfig(
                model=str(model),
                tokens=str(d / "tokens.txt"),
                data_dir=str(d / "espeak-ng-data"),
                noise_scale=0.0,  # no random sampling: the same audio on every run
                noise_scale_w=0.0,
            ),
            num_threads=2,
        )
    )
    return so.OfflineTts(cfg)


def say(tts: so.OfflineTts, text: str) -> np.ndarray:
    a = tts.generate(text, sid=0, speed=1.0)
    x = np.asarray(a.samples, np.float32)
    g = np.gcd(RATE, a.sample_rate)
    return resample_poly(x, RATE // g, a.sample_rate // g).astype(np.float32)


def energy_db(x: np.ndarray) -> np.ndarray:
    fr = x[: len(x) // HOP * HOP].reshape(-1, HOP)
    e = 10 * np.log10(np.mean(fr**2, axis=1) + 1e-12)
    return e - e.max()


def trim(x: np.ndarray, margin_ms: int = 30) -> np.ndarray:
    """Cut leading and trailing silence (below -40 dB of the peak frame)."""
    act = np.where(energy_db(x) > -40)[0]
    m = margin_ms * RATE // 1000
    return x[max(0, act[0] * HOP - m) : min(len(x), (act[-1] + 1) * HOP + m)]


def comma_gap(x: np.ndarray, frac: float) -> int | None:
    """Centre of the quiet gap nearest the expected position of the comma, or None.
    Tries a strict definition of "quiet" first, then looser ones."""
    e = energy_db(x)
    for level, min_frames in ((-35, 5), (-30, 4), (-25, 3)):
        quiet = e < level
        gaps, i = [], 0
        while i < len(quiet):
            if quiet[i]:
                j = i
                while j < len(quiet) and quiet[j]:
                    j += 1
                if j - i >= min_frames and i > 0 and j < len(quiet):  # inside the speech
                    gaps.append((i, j))
                i = j
            else:
                i += 1
        want = frac * len(quiet)
        near = [g for g in gaps if abs((g[0] + g[1]) / 2 - want) < 0.25 * len(quiet)]
        if near:
            a, b = min(near, key=lambda g: abs((g[0] + g[1]) / 2 - want))
            return (a + b) // 2 * HOP
    return None


def write(path: Path, x: np.ndarray) -> None:
    wavfile.write(path, RATE, (np.clip(x, -1, 1) * 32767).astype(np.int16))


def main(root: Path) -> None:
    out = root / "turns"
    out.mkdir(parents=True, exist_ok=True)
    labels, skipped = [], []
    for lang, name in VOICES.items():
        tts = voice(root, name)
        comma = "،" if lang == "ar" else ","
        for k, (pre, post) in enumerate(tts_scripts.MID[lang]):
            for variant in tts_scripts.VARIANTS:
                cid = f"{lang}-mid{k:02d}-{variant}"
                if variant == "split":
                    a, b = trim(say(tts, pre)), trim(say(tts, post))
                    body, cut = np.concatenate([a, b]), len(a)
                else:
                    body = trim(say(tts, f"{pre}{comma} {post}"))
                    found = comma_gap(body, len(pre) / (len(pre) + len(post) + 2))
                    # the cut must sit where the first part ends when spoken alone (within
                    # 10% + 60 ms), or the gap found was between two other words
                    alone = len(trim(say(tts, pre)))
                    if found is None or abs(found - alone) > 0.10 * alone + 0.06 * RATE:
                        skipped.append(cid)
                        continue
                    cut = found
                labels.append(
                    {
                        "id": cid,
                        "lang": lang,
                        "kind": "mid",
                        "variant": variant,
                        "cut": int(cut),
                        "text_at_pause": pre,
                        "text": f"{pre} {post}",
                    }
                )
                write(out / f"{cid}.wav", body)
        for k, (s1, s2) in enumerate(tts_scripts.SENTENCE[lang]):
            cid = f"{lang}-sent{k:02d}"
            a, b = trim(say(tts, s1)), trim(say(tts, s2))
            labels.append(
                {
                    "id": cid,
                    "lang": lang,
                    "kind": "sentence",
                    "variant": "split",
                    "cut": len(a),
                    "text_at_pause": s1,
                    "text": f"{s1} {s2}",
                }
            )
            write(out / f"{cid}.wav", np.concatenate([a, b]))
    index = {"cases": labels, "skipped": skipped}
    (out / "labels.json").write_text(json.dumps(index, ensure_ascii=False, indent=1))
    print(f"{len(labels)} cases written to {out}; comma gap not found: {skipped or 'none'}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
