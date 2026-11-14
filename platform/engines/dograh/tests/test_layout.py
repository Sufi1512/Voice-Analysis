"""T1: platform layout and engine pins (AC-1 pins, AC-9). Plain pytest, no Dograh needed."""

from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parents[1]
PLATFORM = ENGINE_DIR.parents[1]
REPO = PLATFORM.parent

DOGRAH_SHA = "d672de2947da691fbc4542b62b914547a80e01ab"
PIPECAT_SHA = "9ac08e90be4bb83e506f3d10deaa8e6d31588547"


def read_lock() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (ENGINE_DIR / "ENGINE.lock").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def test_engine_lock_pins_audited_commits():
    lock = read_lock()
    assert lock["DOGRAH_REPO"] == "https://github.com/Sufi1512/dograh.git"
    assert lock["DOGRAH_COMMIT"] == DOGRAH_SHA
    assert lock["PIPECAT_REPO"] == "https://github.com/dograh-hq/pipecat.git"
    assert lock["PIPECAT_COMMIT"] == PIPECAT_SHA


def test_patch_matches_integration_copy():
    ours = ENGINE_DIR / "patches" / "0001-nexora-noise-engine.patch"
    theirs = REPO / "integrations" / "dograh" / "0001-nexora-noise-engine.patch"
    assert ours.read_bytes() == theirs.read_bytes()


def test_platform_folders_have_readmes():
    for name in ("services", "apps", "packages", "sdks"):
        readme = PLATFORM / name / "README.md"
        assert readme.is_file(), f"{name}/README.md missing"
        text = readme.read_text()
        assert "P1" in text or "P2" in text or "P3" in text or "P5" in text, f"{name}: no phase named"


def test_engine_readme_exists():
    assert (ENGINE_DIR / "README.md").is_file()
