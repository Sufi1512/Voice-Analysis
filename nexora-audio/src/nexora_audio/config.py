"""Validated SDK configuration."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

SUPPORTED_SAMPLE_RATES: tuple[int, ...] = (8000, 16000, 22050, 24000, 32000, 44100, 48000)

NoiseBackend = Literal["auto", "rnnoise", "webrtc"]


class NexoraConfig(BaseModel):
    """Configuration for :class:`nexora_audio.NexoraAudio`.

    Instances are immutable; create a new one (``cfg.model_copy(update=...)``) to change settings.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Stream format
    sample_rate: int = Field(48000, description="I/O sample rate in Hz.")
    channels: int = Field(1, ge=1, le=2, description="1 = mono, 2 = stereo.")
    frame_ms: float = Field(
        10.0, ge=5.0, le=100.0, description="Chunk duration delivered by streams, in ms."
    )

    # Features
    noise_cancellation: bool = True
    noise_cancellation_strength: float = Field(1.0, ge=0.0, le=1.0)
    noise_backend: NoiseBackend = "auto"
    voice_isolation: bool = False
    echo_cancellation: bool = False
    auto_gain_control: bool = False
    agc_target_dbfs: float = Field(-18.0, ge=-31.0, le=0.0)
    vad: bool = False
    vad_threshold: float = Field(0.5, gt=0.0, lt=1.0)

    # Streaming
    output_queue_chunks: int = Field(
        100, ge=1, description="Max processed chunks buffered before the oldest are dropped."
    )

    @model_validator(mode="after")
    def _check_format(self) -> Self:
        if self.sample_rate not in SUPPORTED_SAMPLE_RATES:
            raise ValueError(
                f"sample_rate must be one of {SUPPORTED_SAMPLE_RATES}, got {self.sample_rate}"
            )
        samples = self.sample_rate * self.frame_ms / 1000.0
        if abs(samples - round(samples)) > 1e-9:
            raise ValueError(
                f"frame_ms={self.frame_ms} gives a non-integer number of samples "
                f"({samples:.3f}) at {self.sample_rate} Hz"
            )
        return self

    @property
    def frame_samples(self) -> int:
        """Samples per channel in one chunk."""
        return round(self.sample_rate * self.frame_ms / 1000.0)

    def requested_features(self) -> list[str]:
        """Names of features switched on, in pipeline order."""
        order = [
            ("echo_cancellation", self.echo_cancellation),
            ("noise_cancellation", self.noise_cancellation),
            ("voice_isolation", self.voice_isolation),
            ("auto_gain_control", self.auto_gain_control),
            ("vad", self.vad),
        ]
        return [name for name, enabled in order if enabled]
