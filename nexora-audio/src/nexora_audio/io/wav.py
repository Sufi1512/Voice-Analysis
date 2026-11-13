"""Streaming file processing (WAV, FLAC and other formats libsndfile supports)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np

from nexora_audio.core.pipeline import Pipeline
from nexora_audio.exceptions import AudioFormatError, BackendError
from nexora_audio.utils.audio_utils import Float32Array
from nexora_audio.utils.metrics import TimingStats


@dataclass(frozen=True, slots=True)
class ProcessingReport:
    """Summary of a :meth:`NexoraAudio.process_file` run.

    ``real_time_factor`` is processing time divided by audio duration; below 1.0
    means faster than real time. Timing covers processing only, not file I/O.
    """

    input_path: str
    output_path: str
    sample_rate: int
    channels: int
    frames: int
    duration_s: float
    processing_s: float
    real_time_factor: float
    latency_compensated_ms: float
    block_p50_ms: float
    block_p99_ms: float
    backends: tuple[str, ...]


def _soundfile() -> ModuleType:
    try:
        import soundfile
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise BackendError(
            "file processing needs the 'soundfile' package: pip install 'nexora-audio[io]'"
        ) from exc
    module: ModuleType = soundfile
    return module


def file_format(path: str | Path) -> tuple[int, int]:
    """Return ``(sample_rate, channels)`` of an audio file."""
    sf = _soundfile()
    try:
        info = sf.info(str(path))
    except (RuntimeError, sf.LibsndfileError) as exc:
        raise AudioFormatError(f"cannot read audio file {path}: {exc}") from exc
    return int(info.samplerate), int(info.channels)


def process_file(
    pipeline: Pipeline,
    input_path: str | Path,
    output_path: str | Path,
    *,
    block_frames: int = 4800,
    subtype: str | None = None,
) -> ProcessingReport:
    """Stream ``input_path`` through ``pipeline`` into ``output_path``.

    The output has the same rate, channel count and length as the input. The
    pipeline's algorithmic latency is removed so output sample *n* lines up with
    input sample *n*. The pipeline must match the file's rate and channel count.
    """
    sf = _soundfile()
    in_path, out_path = Path(input_path), Path(output_path)
    if in_path.resolve() == out_path.resolve():
        raise AudioFormatError("output_path must differ from input_path")

    with sf.SoundFile(str(in_path)) as fin:
        rate, channels, total = fin.samplerate, fin.channels, fin.frames
        if rate != pipeline.sample_rate or channels != pipeline.channels:
            raise AudioFormatError(
                f"pipeline is {pipeline.sample_rate} Hz/{pipeline.channels} ch, "
                f"file is {rate} Hz/{channels} ch"
            )
        out_subtype = subtype or (
            fin.subtype if sf.check_format(_format_for(out_path, fin), fin.subtype) else None
        )
        skip = round(pipeline.latency.algorithmic_ms * rate / 1000.0)
        timer = TimingStats()
        state: dict[str, Any] = {"skip": skip, "written": 0}

        with sf.SoundFile(
            str(out_path),
            "w",
            samplerate=rate,
            channels=channels,
            subtype=out_subtype,
            format=_format_for(out_path, fin),
        ) as fout:

            def emit(block: Float32Array) -> None:
                if state["skip"]:
                    drop = min(state["skip"], block.shape[1])
                    block = block[:, drop:]
                    state["skip"] -= drop
                room = total - state["written"]
                block = block[:, :room]
                if block.shape[1]:
                    fout.write(np.clip(block.T, -1.0, 1.0))
                    state["written"] += block.shape[1]

            for data in fin.blocks(blocksize=block_frames, dtype="float32", always_2d=True):
                planar = np.ascontiguousarray(data.T)
                t0 = time.perf_counter()
                out = pipeline.process(planar)
                timer.add(time.perf_counter() - t0)
                emit(out)
            t0 = time.perf_counter()
            tail = pipeline.flush()
            timer.add(time.perf_counter() - t0)
            emit(tail)

    duration = total / rate if rate else 0.0
    return ProcessingReport(
        input_path=str(in_path),
        output_path=str(out_path),
        sample_rate=rate,
        channels=channels,
        frames=int(state["written"]),
        duration_s=duration,
        processing_s=timer.total_s,
        real_time_factor=timer.total_s / duration if duration else 0.0,
        latency_compensated_ms=skip * 1000.0 / rate if rate else 0.0,
        block_p50_ms=timer.p50_ms,
        block_p99_ms=timer.p99_ms,
        backends=tuple(p.name for p in pipeline.processors),
    )


def _format_for(path: Path, fin: Any) -> str:
    ext = path.suffix.lower().lstrip(".")
    known = {"wav": "WAV", "flac": "FLAC", "ogg": "OGG", "aiff": "AIFF", "aif": "AIFF"}
    return known.get(ext, str(fin.format))
