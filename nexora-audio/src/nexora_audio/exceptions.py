"""Exception hierarchy for nexora-audio.

Every error raised on purpose by the SDK derives from :class:`NexoraError`, so
applications can catch SDK failures with a single ``except`` clause.
"""

from __future__ import annotations


class NexoraError(Exception):
    """Base class for all nexora-audio errors."""


class ConfigurationError(NexoraError, ValueError):
    """The supplied configuration is invalid."""


class FeatureUnavailableError(NexoraError):
    """A requested feature has no working backend on this system.

    Raised instead of silently passing audio through unprocessed.
    """

    def __init__(self, feature: str, reason: str) -> None:
        self.feature = feature
        self.reason = reason
        super().__init__(f"Feature '{feature}' is unavailable: {reason}")


class BackendError(NexoraError):
    """A processing backend failed to load or to process audio."""


class AudioFormatError(NexoraError, ValueError):
    """Audio data has an unsupported shape, dtype, rate or contains non-finite values."""


class NotInitializedError(NexoraError, RuntimeError):
    """An operation needs :meth:`NexoraAudio.initialize` to be called first."""


class DeviceError(NexoraError):
    """An audio device could not be opened or used."""


class DeviceDisconnectedError(DeviceError):
    """An audio device disappeared and could not be recovered."""
