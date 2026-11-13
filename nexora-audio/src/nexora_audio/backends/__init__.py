"""Built-in processing backends."""

from __future__ import annotations

from nexora_audio.backends import enhancer, rnnoise
from nexora_audio.core.capabilities import BackendRegistry

BUILTIN_SPECS = (rnnoise.SPEC, enhancer.ENHANCER_SPEC, enhancer.AGC_SPEC)


def register_builtin_backends(registry: BackendRegistry) -> None:
    """Register every built-in backend. Availability is decided later by each probe."""
    for spec in BUILTIN_SPECS:
        if spec.name not in {s.name for s in registry.backends(spec.feature)}:
            registry.register(spec)
