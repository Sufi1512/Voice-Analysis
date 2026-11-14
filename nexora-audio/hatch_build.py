"""Wheel build hook: platform wheels carry only their own native libraries.

Set ``NEXORA_WHEEL_PLATFORM`` to one of ``PLATFORM_TAGS`` and remove the other platforms'
folders from ``src/nexora_audio/_native/`` first (CI does both, see
``.github/workflows/wheels.yml``); the wheel is then tagged for that platform. Without the
variable the wheel is ``py3-none-any`` with whatever libraries are present (development).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

# glibc 2.35: the newest symbol libdf needs (see _native/PROVENANCE.md)
PLATFORM_TAGS = {
    "linux-x86_64": "manylinux_2_35_x86_64",
    "linux-aarch64": "manylinux_2_35_aarch64",
    "darwin-aarch64": "macosx_11_0_arm64",
    "darwin-x86_64": "macosx_11_0_x86_64",
}


class CustomBuildHook(BuildHookInterface):  # type: ignore[type-arg]
    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        plat = os.environ.get("NEXORA_WHEEL_PLATFORM")
        if not plat or self.target_name != "wheel":
            return
        if plat not in PLATFORM_TAGS:
            raise ValueError(f"NEXORA_WHEEL_PLATFORM must be one of {sorted(PLATFORM_TAGS)}")
        native = Path(self.root) / "src" / "nexora_audio" / "_native"
        dirs = {d.name for d in native.iterdir() if d.is_dir() and d.name in PLATFORM_TAGS}
        if dirs != {plat}:
            raise ValueError(f"_native/ must hold only {plat} for this wheel, found {sorted(dirs)}")
        build_data["pure_python"] = False
        build_data["tag"] = f"py3-none-{PLATFORM_TAGS[plat]}"
