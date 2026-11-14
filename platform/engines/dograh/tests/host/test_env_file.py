"""T6: NEXORA's Dograh settings file holds no secrets (AC-7)."""

import re
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parents[2] / ".env.nexora"


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
