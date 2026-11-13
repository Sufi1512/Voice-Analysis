"""Processor contract shared by every audio-processing stage.

A processor works on fixed-size frames at its own native sample rate. The
:class:`~nexora_audio.core.pipeline.Pipeline` adapts arbitrary chunk sizes and
rates to that contract, so backends never need to buffer or resample.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from nexora_audio.utils.audio_utils import Float32Array


class ProcessorKind(Enum):
    TRANSFORM = "transform"  # returns modified audio of the same shape
    ANALYSIS = "analysis"  # inspects audio, returns results; audio passes unchanged


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    """Output of an analysis processor for one frame.

    ``start_sample`` is in the pipeline's I/O sample-rate timeline.
    """

    processor: str
    start_sample: int
    values: dict[str, Any] = field(default_factory=dict)


class Processor(ABC):
    """Base class for audio processors.

    Subclasses must be usable from a single worker thread; they need not be thread-safe.
    """

    name: str = "processor"
    kind: ProcessorKind = ProcessorKind.TRANSFORM

    @property
    @abstractmethod
    def native_sample_rate(self) -> int:
        """Sample rate the processor operates at, in Hz."""

    @property
    @abstractmethod
    def native_frame_size(self) -> int:
        """Samples per channel in each frame passed to :meth:`process`."""

    @property
    def latency_samples(self) -> int:
        """Algorithmic delay the processor adds, in native-rate samples."""
        return 0

    @property
    def max_channels(self) -> int:
        """Maximum channel count accepted (stereo backends keep one state per channel)."""
        return 2

    @abstractmethod
    def process(self, frame: Float32Array) -> Float32Array:
        """Process one ``(channels, native_frame_size)`` float32 frame.

        TRANSFORM processors return a new array of the same shape.
        ANALYSIS processors must return ``frame`` unchanged and record results via
        :meth:`pop_results`.
        """

    def pop_results(self) -> list[dict[str, Any]]:
        """Return and clear per-frame analysis values accumulated since the last call."""
        return []

    def reset(self) -> None:  # noqa: B027 - optional hook
        """Clear internal state, e.g. between unrelated streams."""

    def close(self) -> None:  # noqa: B027 - optional hook
        """Release native resources. The processor must not be used afterwards."""
