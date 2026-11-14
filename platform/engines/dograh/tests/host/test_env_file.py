"""T6: NEXORA's Dograh settings file holds no secrets (AC-7)."""

import re
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parents[2] / "nexora.env"


def entries() -> dict[str, str]:
    out = {}
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            key, _, value = line.partition("=")
            out[key] = value
    return out


def test_env_nexora_has_no_secrets():
    for key, value in entries().items():
        if re.search(r"KEY|TOKEN|SECRET|PASSWORD|DSN", key):
            assert value == "", f"{key} carries a value"
    assert "POSTHOG_API_KEY" not in entries()


def test_env_nexora_sets_telemetry_off_and_oss():
    assert entries()["ENABLE_TELEMETRY"] == "false"
    assert entries()["DEPLOYMENT_MODE"] == "oss"


def test_env_file_is_tracked_by_git():
    """Regression: the root .gitignore drops `.env.*` files, so a dot-env name never reached CI."""
    import subprocess

    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", ENV_FILE.name], cwd=ENV_FILE.parent,
                             capture_output=True, text=True)
    assert tracked.returncode == 0, f"{ENV_FILE.name} is not committed (ignored by .gitignore?)"
