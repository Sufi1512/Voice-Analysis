"""Validated SDK configuration."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

SUPPORTED_SAMPLE_RATES: tuple[int, ...] = (8000, 16000, 22050, 24000, 32000, 44100, 48000)

NoiseBackend = Literal["auto", "deepfilternet3", "rnnoise", "webrtc"]


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
    noise_cancellation_strength: float = Field(
        1.0,
        ge=0.0,
        le=1.0,
        description="Suppression when no one is speaking (1.0 = maximum, clean pauses).",
    )
    deepfilter_atten_lim_db: float = Field(
        100.0,
        gt=0.0,
        le=100.0,
        description="DeepFilterNet3 maximum attenuation in pauses, dB (100 = no limit).",
    )
    deepfilter_speech_atten_lim_db: float = Field(
        20.0,
        gt=0.0,
        le=100.0,
        description="DeepFilterNet3 maximum attenuation while speech is present, dB.",
    )
    pause_gate_db: float = Field(
        40.0,
        ge=0.0,
        le=80.0,
        description="Extra attenuation applied when no speech is detected (DeepFilterNet3).",
    )
    speech_protection: bool = Field(
        True,
        description=(
            "Use a speech detector (Silero VAD) to suppress less while someone is speaking, "
            "so quiet words don't cut out. Off = noise_cancellation_strength all the time."
        ),
    )
    speech_protection_strength: float = Field(
        0.85,
        ge=0.0,
        le=1.0,
        description="Suppression while speech is present (0.85 caps it at ~16.5 dB).",
    )
    speech_guard: bool = Field(
        True,
        description=(
            "Never remove more than the noise can explain: in frames clearly above the noise "
            "floor that may be speech, restore what the model removed beyond the noise share "
            "(DeepFilterNet3; needs speech_protection)."
        ),
    )
    speech_guard_margin_db: float = Field(
        6.0,
        ge=0.0,
        le=30.0,
        description="Extra removal the speech guard allows beyond the noise share, dB.",
    )
    background_speech_db: float | None = Field(
        17.0,
        ge=3.0,
        le=40.0,
        description=(
            "Speech this many dB below the caller's level is treated as background talk "
            "(TV, colleagues, announcements) and removed in pauses; None disables "
            "(DeepFilterNet3; needs speech_protection)."
        ),
    )
    noise_backend: NoiseBackend = "auto"
    voice_isolation: bool = False
    echo_cancellation: bool = False
    voice_enhancement: bool = Field(
        True, description="80 Hz high-pass, clarity EQ and peak limiter (plus AGC if enabled)."
    )
    clarity_db: float = Field(3.0, ge=0.0, le=9.0, description="Presence boost at 3 kHz, dB.")
    auto_gain_control: bool = Field(
        False,
        description=(
            "Slowly level speech towards agc_target_dbfs. Off by default: it costs a little "
            "intelligibility; turn on when talker volume varies a lot."
        ),
    )
    agc_target_dbfs: float = Field(-20.0, ge=-31.0, le=0.0)
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
        """Names of features switched on, in pipeline order.

        When ``voice_enhancement`` is on, gain control runs inside it, so
        ``auto_gain_control`` is not listed separately.
        """
        order = [
            ("echo_cancellation", self.echo_cancellation),
            ("noise_cancellation", self.noise_cancellation),
            ("voice_isolation", self.voice_isolation),
            ("voice_enhancement", self.voice_enhancement),
            ("auto_gain_control", self.auto_gain_control and not self.voice_enhancement),
            ("vad", self.vad),
        ]
        return [name for name, enabled in order if enabled]
