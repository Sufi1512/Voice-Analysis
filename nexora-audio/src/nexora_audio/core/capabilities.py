"""Backend registry and feature availability reporting.

Backends register a probe that reports whether they can run on this system. The
SDK never pretends to process audio: a feature with no available backend is
reported as unavailable and :meth:`NexoraAudio.initialize` raises.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from nexora_audio.config import NexoraConfig
from nexora_audio.core.processor import Processor

FEATURES: tuple[str, ...] = (
    "noise_cancellation",
    "voice_isolation",
    "echo_cancellation",
    "voice_enhancement",
    "auto_gain_control",
    "vad",
)

_NOT_YET: dict[str, str] = {
    "noise_cancellation": "no noise-cancellation backend is installed or implemented yet",
    "voice_isolation": (
        "no permissively licensed voice-isolation model is available "
        "(see docs/DEPENDENCY_LICENSES.md)"
    ),
    "echo_cancellation": "the bundled WebRTC AEC3 library (libnexora_aec) is not available here",
    "voice_enhancement": "no voice-enhancement backend is installed",
    "auto_gain_control": "no gain-control backend is installed or implemented yet",
    "vad": "no voice-activity-detection backend is installed or implemented yet",
}


@dataclass(frozen=True, slots=True)
class FeatureStatus:
    feature: str
    available: bool
    backend: str | None
    reason: str


Probe = Callable[[], str | None]  # returns None if usable, else a human-readable reason
Factory = Callable[[NexoraConfig], Processor]


@dataclass(frozen=True, slots=True)
class BackendSpec:
    feature: str
    name: str
    probe: Probe
    factory: Factory
    priority: int = 0  # higher wins when several are available


class BackendRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, list[BackendSpec]] = {f: [] for f in FEATURES}

    def register(self, spec: BackendSpec) -> None:
        if spec.feature not in self._specs:
            raise ValueError(f"unknown feature {spec.feature!r}; expected one of {FEATURES}")
        if any(s.name == spec.name for s in self._specs[spec.feature]):
            raise ValueError(f"backend {spec.name!r} already registered for {spec.feature}")
        self._specs[spec.feature].append(spec)
        self._specs[spec.feature].sort(key=lambda s: -s.priority)

    def backends(self, feature: str) -> list[BackendSpec]:
        return list(self._specs[feature])

    def resolve(
        self, feature: str, preferred: str = "auto"
    ) -> tuple[FeatureStatus, BackendSpec | None]:
        specs = self._specs[feature]
        if preferred != "auto":
            specs = [s for s in specs if s.name == preferred]
            if not specs:
                reason = f"backend {preferred!r} is not registered for {feature}"
                return FeatureStatus(feature, False, None, reason), None
        if not specs:
            return FeatureStatus(feature, False, None, _NOT_YET[feature]), None
        reasons = []
        for spec in specs:
            problem = spec.probe()
            if problem is None:
                return FeatureStatus(feature, True, spec.name, "ok"), spec
            reasons.append(f"{spec.name}: {problem}")
        return FeatureStatus(feature, False, None, "; ".join(reasons)), None

    def status(self, feature: str, preferred: str = "auto") -> FeatureStatus:
        return self.resolve(feature, preferred)[0]

    def capabilities(self) -> dict[str, FeatureStatus]:
        return {f: self.status(f) for f in FEATURES}


default_registry = BackendRegistry()
