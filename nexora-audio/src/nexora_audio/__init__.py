"""nexora-audio: real-time AI audio processing SDK."""

from nexora_audio.backends import register_builtin_backends
from nexora_audio.client import NexoraAudio
from nexora_audio.config import NexoraConfig
from nexora_audio.core.capabilities import FeatureStatus, default_registry
from nexora_audio.core.pipeline import LatencyReport
from nexora_audio.core.processor import AnalysisResult
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
from nexora_audio.io.wav import ProcessingReport
from nexora_audio.version import __version__

register_builtin_backends(default_registry)

__all__ = [
    "AnalysisResult",
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
    "ProcessingReport",
    "__version__",
]
