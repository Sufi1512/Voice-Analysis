"""Built-in processing backends."""

from __future__ import annotations

from nexora_audio.backends import rnnoise
from nexora_audio.core.capabilities import BackendRegistry


def register_builtin_backends(registry: BackendRegistry) -> None:
    """Register every built-in backend. Availability is decided later by each probe."""
    names = {s.name for s in registry.backends(rnnoise.SPEC.feature)}
    if rnnoise.SPEC.name not in names:
        registry.register(rnnoise.SPEC)
