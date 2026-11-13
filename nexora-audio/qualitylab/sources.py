"""Pinned public test audio and the speech-to-text model, fetched into a local cache.

Nothing here is committed to the repository: files are downloaded at a pinned commit or
release, so every run uses exactly the same audio. Licences are listed in
``qualitylab/SOURCES.md``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tarfile
import urllib.request
from functools import cache
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parent
JFK = ROOT.parent / "tests" / "fixtures" / "jfk_inaugural_16k.wav"

MSSNSD_REPO = "https://github.com/microsoft/MS-SNSD"
MSSNSD_COMMIT = "fe61c4ba0d9ac8dd7e23d719cc79f8947e1dc742"
CLEAN_FILES = [f"clean_test/clnsp{i}.wav" for i in range(24)]
# One NEXORA noise name -> MS-SNSD test-split files (Freesound CC0 / DEMAND CC BY-SA 3.0).
REAL_NOISES: dict[str, list[str]] = {
    "air_conditioner": ["noise_test/AirConditioner_1.wav", "noise_test/AirConditioner_2.wav"],
    "airport_pa": ["noise_test/AirportAnnouncements_1.wav"],
    "babble": ["noise_test/Babble_1.wav", "noise_test/Babble_2.wav"],
    "copy_machine": ["noise_test/CopyMachine_1.wav"],
    "munching": ["noise_test/Munching_1.wav"],
    "neighbor": ["noise_test/Neighbor_1.wav"],
    "door": ["noise_test/ShuttingDoor_1.wav"],
    "typing": ["noise_test/Typing_1.wav"],
    "vacuum": ["noise_test/VacuumCleaner_1.wav"],
}

STT_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
    "sherpa-onnx-whisper-tiny.en.tar.bz2"
)
STT_DIR_NAME = "sherpa-onnx-whisper-tiny.en"


def cache_dir() -> Path:
    path = Path(os.environ.get("NEXORA_QL_CACHE", ROOT / ".cache"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def mssnsd_dir() -> Path:
    return cache_dir() / "MS-SNSD"


def _git(*args: str, cwd: Path | None = None) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def fetch_mssnsd() -> Path:
    """Sparse-fetch only the files we use, at the pinned commit."""
    dest = mssnsd_dir()
    wanted = ["/LICENSE", "/README.md"] + [
        "/" + f for f in CLEAN_FILES + [p for ps in REAL_NOISES.values() for p in ps]
    ]
    if not (dest / ".git").exists():
        if dest.exists():
            shutil.rmtree(dest)
        _git("clone", "--filter=blob:none", "--no-checkout", "--sparse", MSSNSD_REPO, str(dest))
    _git("sparse-checkout", "set", "--no-cone", *wanted, cwd=dest)
    _git("checkout", "--quiet", MSSNSD_COMMIT, cwd=dest)
    missing = [p for p in wanted if not (dest / p.lstrip("/")).exists()]
    if missing:
        raise RuntimeError(f"MS-SNSD files missing after fetch: {missing[:3]}")
    return dest


def fetch_stt() -> Path:
    dest = cache_dir() / STT_DIR_NAME
    if (dest / "tiny.en-tokens.txt").exists():
        return dest
    archive = cache_dir() / "whisper-tiny.en.tar.bz2"
    urllib.request.urlretrieve(STT_URL, archive)
    with tarfile.open(archive) as tar:
        tar.extractall(cache_dir(), filter="data")
    archive.unlink()
    return dest


def stt_dir() -> Path | None:
    dest = cache_dir() / STT_DIR_NAME
    return dest if (dest / "tiny.en-tokens.txt").exists() else None


def have_mssnsd() -> bool:
    return (mssnsd_dir() / CLEAN_FILES[-1]).exists()


@cache
def load16k(path: str) -> np.ndarray:
    x, sr = sf.read(path, dtype="float32", always_2d=False)
    if x.ndim > 1:
        x = x.mean(axis=1)
    if sr != 16000:
        raise ValueError(f"{path}: expected 16 kHz, got {sr}")
    return np.ascontiguousarray(x, dtype=np.float32)


def speech_clips() -> dict[str, np.ndarray]:
    """Speech clips by id: the MS-SNSD clean test clips.

    The JFK fixture is used only when MS-SNSD is missing: it is a 1961 recording with
    its own crowd noise and hiss, so it is not a clean reference (the speech-cut metric
    counts removing that crowd as removing speech).
    """
    if not have_mssnsd():
        return {"jfk": load16k(str(JFK))}
    return {Path(f).stem: load16k(str(mssnsd_dir() / f)) for f in CLEAN_FILES}


def real_noise(name: str, index: int = 0) -> np.ndarray:
    files = REAL_NOISES[name]
    return load16k(str(mssnsd_dir() / files[index % len(files)]))
