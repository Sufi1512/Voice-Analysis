"""T6: Dograh starts with telemetry off under NEXORA's settings (AC-7).

Dograh has two telemetry paths: PostHog (``api.services.posthog_client``, needs
``POSTHOG_API_KEY``) and Sentry (``api.app``, enabled in OSS mode only when
``ENABLE_TELEMETRY`` is true). Each check runs in a fresh interpreter whose environment
holds only ``.env.nexora`` and the dummy service URLs, so nothing leaks in from the host.
"""

import os
import subprocess
import sys
from pathlib import Path

import api

DOGRAH_ROOT = Path(api.__file__).resolve().parents[1]
ENV_FILE = Path(os.environ["NEXORA_ENV_FILE"])


def nexora_env(**extra: str) -> dict[str, str]:
    env = {"PATH": os.environ["PATH"], "PYTHONPATH": str(DOGRAH_ROOT),
           "DATABASE_URL": "postgresql+asyncpg://dummy:dummy@localhost/dummy",
           "REDIS_URL": "redis://localhost:6379/0", "MINIO_PUBLIC_ENDPOINT": "http://localhost:9000"}
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            key, _, value = line.partition("=")
            env[key] = value
    env.update(extra)
    return env


def run(code: str, **extra: str) -> str:
    res = subprocess.run([sys.executable, "-c", code], cwd=DOGRAH_ROOT, env=nexora_env(**extra),
                         capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stderr[-2000:]
    return res.stdout.strip().splitlines()[-1]


def test_env_nexora_turns_telemetry_off():
    out = run("import api.constants as c; print(c.ENABLE_TELEMETRY, c.DEPLOYMENT_MODE, bool(c.POSTHOG_API_KEY))")
    assert out == "False oss False"


def test_posthog_client_is_never_created():
    out = run("from api.services.posthog_client import get_posthog; print(get_posthog() is None)")
    assert out == "True"


def test_sentry_gate_stays_closed_even_with_a_dsn():
    # The exact condition in api/app.py, evaluated with Dograh's constants.
    out = run("import api.constants as c; "
              "print(bool(c.SENTRY_DSN and (c.DEPLOYMENT_MODE != 'oss' or (c.DEPLOYMENT_MODE == 'oss' and c.ENABLE_TELEMETRY))))",
              SENTRY_DSN="https://key@example.invalid/1")
    assert out == "False"


def test_default_without_nexora_settings_would_send_telemetry():
    """Control: Dograh's own default is telemetry on, so the setting matters."""
    res = subprocess.run([sys.executable, "-c", "import api.constants as c; print(c.ENABLE_TELEMETRY)"],
                         cwd=DOGRAH_ROOT, capture_output=True, text=True, timeout=120,
                         env={"PATH": os.environ["PATH"], "PYTHONPATH": str(DOGRAH_ROOT),
                              "DATABASE_URL": "postgresql+asyncpg://d:d@localhost/d",
                              "REDIS_URL": "redis://localhost:6379/0", "MINIO_PUBLIC_ENDPOINT": "http://localhost:9000"})
    assert res.returncode == 0, res.stderr[-2000:]
    assert res.stdout.strip().splitlines()[-1] == "True"
