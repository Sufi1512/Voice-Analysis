"""Public entry point."""

from __future__ import annotations

from types import TracebackType
from typing import Any, Self

from pydantic import ValidationError

from nexora_audio.config import NexoraConfig
from nexora_audio.core.capabilities import BackendRegistry, FeatureStatus, default_registry
from nexora_audio.core.pipeline import LatencyReport, Pipeline
from nexora_audio.core.processor import Processor
from nexora_audio.exceptions import ConfigurationError, FeatureUnavailableError, NotInitializedError


class NexoraAudio:
    """Real-time audio processing client.

    Example::

        audio = NexoraAudio(noise_cancellation=True, sample_rate=48000)
        print(audio.capabilities())
        audio.initialize()   # raises FeatureUnavailableError if a feature can't run here

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
        processors: list[Processor] = []
        try:
            for feature in self._config.requested_features():
                preferred = (
                    self._config.noise_backend if feature == "noise_cancellation" else "auto"
                )
                status, spec = self._registry.resolve(feature, preferred)
                if spec is None:
                    raise FeatureUnavailableError(feature, status.reason)
                processors.append(spec.factory(self._config))
        except BaseException:
            for proc in processors:
                proc.close()
            raise
        self._pipeline = Pipeline(self._config.sample_rate, self._config.channels, processors)

    @property
    def latency(self) -> LatencyReport:
        return self._require_pipeline().latency

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
