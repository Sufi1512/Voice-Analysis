"""nexora-audio: real-time AI audio processing SDK."""

from nexora_audio.client import NexoraAudio
from nexora_audio.config import NexoraConfig
from nexora_audio.core.capabilities import FeatureStatus
from nexora_audio.core.pipeline import LatencyReport
from nexora_audio.exceptions import (
    AudioFormatError,
    BackendError,
    ConfigurationError,
    DeviceDisconnectedError,
    DeviceError,
    FeatureUnavailableError,
    NexoraError,
    NotInitializedError,
)
from nexora_audio.version import __version__

__all__ = [
    "AudioFormatError",
    "BackendError",
    "ConfigurationError",
    "DeviceDisconnectedError",
    "DeviceError",
    "FeatureStatus",
    "FeatureUnavailableError",
    "LatencyReport",
    "NexoraAudio",
    "NexoraConfig",
    "NexoraError",
    "NotInitializedError",
    "__version__",
]
