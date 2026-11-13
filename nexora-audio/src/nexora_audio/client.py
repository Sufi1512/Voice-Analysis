"""Public entry point."""

from __future__ import annotations

import time
from pathlib import Path
from types import TracebackType
from typing import Any, Self

import numpy as np
from numpy.typing import ArrayLike, NDArray
from pydantic import ValidationError

from nexora_audio.config import NexoraConfig
from nexora_audio.core.capabilities import (
    BackendRegistry,
    BackendSpec,
    FeatureStatus,
    default_registry,
)
from nexora_audio.core.pipeline import LatencyReport, Pipeline
from nexora_audio.core.processor import AnalysisResult, Processor
from nexora_audio.exceptions import (
    AudioFormatError,
    ConfigurationError,
    FeatureUnavailableError,
    NotInitializedError,
)
from nexora_audio.io.wav import ProcessingReport, file_format, process_file
from nexora_audio.utils.audio_utils import to_interleaved, to_planar_float32
from nexora_audio.utils.metrics import TimingStats


class NexoraAudio:
    """Real-time audio processing client.

    Example::

        with NexoraAudio(noise_cancellation=True, sample_rate=48000) as audio:
            clean = audio.process_chunk(chunk)          # streaming, any chunk size
            report = audio.process_file("in.wav", "out.wav")

    ``initialize()`` (or entering the ``with`` block) raises
    :class:`FeatureUnavailableError` if a requested feature can't run here.

    Settings may be given as keyword arguments or as a :class:`NexoraConfig`.
    """

    def __init__(
        self,
        config: NexoraConfig | None = None,
        *,
        registry: BackendRegistry | None = None,
        **settings: Any,
    ) -> None:
        if config is not None and settings:
            raise ConfigurationError("pass either a NexoraConfig or keyword settings, not both")
        try:
            self._config = config if config is not None else NexoraConfig(**settings)
        except ValidationError as exc:
            raise ConfigurationError(str(exc)) from exc
        self._registry = registry or default_registry
        self._pipeline: Pipeline | None = None
        self._specs: list[BackendSpec] = []
        self.timing = TimingStats()
        """Processing time per :meth:`process_chunk` call."""

    @property
    def config(self) -> NexoraConfig:
        return self._config

    @property
    def initialized(self) -> bool:
        return self._pipeline is not None

    def capabilities(self) -> dict[str, FeatureStatus]:
        """Availability of every feature on this system, with the backend that would run it."""
        caps = self._registry.capabilities()
        caps["noise_cancellation"] = self._registry.status(
            "noise_cancellation", self._config.noise_backend
        )
        return caps

    def initialize(self) -> None:
        """Load backends for every requested feature and build the pipeline.

        Raises:
            FeatureUnavailableError: a requested feature has no usable backend.
        """
        if self._pipeline is not None:
            return
        specs: list[BackendSpec] = []
        for feature in self._config.requested_features():
            preferred = self._config.noise_backend if feature == "noise_cancellation" else "auto"
            status, spec = self._registry.resolve(feature, preferred)
            if spec is None:
                raise FeatureUnavailableError(feature, status.reason)
            specs.append(spec)
        self._specs = specs
        self._pipeline = self._build_pipeline(self._config.sample_rate, self._config.channels)

    @property
    def latency(self) -> LatencyReport:
        return self._require_pipeline().latency

    @property
    def backends(self) -> list[str]:
        """Names of the backends running, in pipeline order."""
        return [p.name for p in self._require_pipeline().processors]

    def process_chunk(self, audio_chunk: ArrayLike) -> NDArray[Any]:
        """Process one chunk of a continuous stream.

        Accepts 1-D mono or ``(samples, channels)`` audio as int16, int32 or float.
        Returns the processed audio available so far, in the same layout: int16
        input gives int16 output, anything else gives float32. Calls share state,
        so feed consecutive chunks of one stream. Chunks that are multiples of
        ``config.frame_samples`` come back at the same length, delayed by
        :attr:`latency`; other sizes may return more or fewer samples per call.
        Call :meth:`flush` at the end of a stream and :meth:`reset` before an
        unrelated one.
        """
        pipeline = self._require_pipeline()
        src = np.asarray(audio_chunk)
        planar = to_planar_float32(src, self._config.channels)
        t0 = time.perf_counter()
        out = pipeline.process(planar)
        self.timing.add(time.perf_counter() - t0)
        return self._like_input(out, src)

    def flush(self, like: ArrayLike | None = None) -> NDArray[Any]:
        """Return the audio still buffered in the pipeline (end of stream).

        The result is 2-D ``(samples, channels)`` float32 unless ``like`` is given,
        in which case it follows that array's layout and dtype.
        """
        out = self._require_pipeline().flush()
        ref = np.asarray(like) if like is not None else np.zeros((0, self._config.channels))
        return self._like_input(out, ref)

    def pop_results(self) -> list[AnalysisResult]:
        """Analysis results (e.g. VAD probabilities and speech start/end events) produced
        since the last call. ``start_sample`` is in the stream's sample timeline."""
        return self._require_pipeline().pop_results()

    def reset(self) -> None:
        """Clear stream state so the next chunk starts a new, unrelated stream."""
        self._require_pipeline().reset()
        self.timing.reset()

    def process_file(
        self,
        input_path: str | Path,
        output_path: str | Path,
        *,
        block_frames: int = 4800,
    ) -> ProcessingReport:
        """Process an audio file into ``output_path``, streaming in blocks.

        Works at the file's own sample rate and channel count (mono or stereo),
        using fresh backend instances, so it doesn't disturb a live stream. Output
        keeps the input's length and is aligned to it (pipeline latency removed).
        """
        self._require_pipeline()
        rate, channels = file_format(input_path)
        if channels > 2:
            raise AudioFormatError(f"only mono and stereo files are supported, got {channels}")
        pipeline = self._build_pipeline(rate, channels)
        try:
            return process_file(pipeline, input_path, output_path, block_frames=block_frames)
        finally:
            pipeline.close()

    def close(self) -> None:
        """Release all backend resources. Safe to call more than once."""
        if self._pipeline is not None:
            self._pipeline.close()
            self._pipeline = None

    def __enter__(self) -> Self:
        self.initialize()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def _require_pipeline(self) -> Pipeline:
        if self._pipeline is None:
            raise NotInitializedError("call initialize() first")
        return self._pipeline

    def _build_pipeline(self, sample_rate: int, channels: int) -> Pipeline:
        cfg = self._config.model_copy(update={"channels": channels})
        processors: list[Processor] = []
        try:
            for spec in self._specs:
                processors.append(spec.factory(cfg))
            return Pipeline(sample_rate, channels, processors)
        except BaseException:
            for proc in processors:
                proc.close()
            raise

    @staticmethod
    def _like_input(planar: NDArray[np.float32], src: NDArray[Any]) -> NDArray[Any]:
        dtype = np.int16 if src.dtype == np.int16 else np.float32
        out = to_interleaved(planar, dtype)
        return out[:, 0] if src.ndim == 1 else out
