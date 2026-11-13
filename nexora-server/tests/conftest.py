from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from nexora_server.app import create_app
from nexora_server.settings import Settings

ADMIN = "test-superadmin-key"
SPEECH = Path(__file__).parents[2] / "nexora-audio" / "tests" / "fixtures" / "jfk_inaugural_16k.wav"


def make_settings(tmp_path: Path, **overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "database_url": f"sqlite:///{tmp_path / 'nexora.db'}",
        "secret_key": "test-secret-0123456789abcdef0123456789abcdef",
        "admin_api_key": ADMIN,
        "deployment_mode": "self_hosted",
        "max_sessions": 8,
        "worker_threads": 2,
        "log_level": "WARNING",
    }
    base.update(overrides)
    return Settings.model_validate(base)


@pytest.fixture
def make_client(tmp_path: Path) -> Iterator[Any]:
    clients: list[TestClient] = []

    def factory(**overrides: Any) -> TestClient:
        c = TestClient(create_app(make_settings(tmp_path, **overrides), prewarm=False))
        c.__enter__()
        clients.append(c)
        return c

    yield factory
    for c in clients:
        c.__exit__(*sys.exc_info())


@pytest.fixture
def client(make_client: Any) -> TestClient:
    c: TestClient = make_client()
    return c


def admin() -> dict[str, str]:
    return {"Authorization": f"Bearer {ADMIN}"}


def bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def new_org(client: TestClient, **fields: Any) -> tuple[str, str]:
    body = {"name": "Acme", **fields}
    r = client.post("/v1/orgs", json=body, headers=admin())
    assert r.status_code == 201, r.text
    data = r.json()
    return data["organization"]["id"], data["api_key"]


def speech_pcm16(pad_s: float = 0.5, seconds: float | None = None) -> bytes:
    x, sr = sf.read(str(SPEECH), dtype="float32")
    if seconds is not None:
        x = x[: int(seconds * sr)]
    z = np.zeros(int(pad_s * sr), np.float32)
    s = np.concatenate([z, x, z]) * 0.8
    return (np.clip(s, -1, 1) * 32767).astype("<i2").tobytes()


def chunks(data: bytes, ms: int = 20, rate: int = 16000, width: int = 2) -> list[bytes]:
    step = rate * ms // 1000 * width
    return [data[i : i + step] for i in range(0, len(data), step)]


def drain(ws: Any) -> tuple[list[dict[str, Any]], bytes, int | None]:
    """Read until the server closes: (json messages, audio bytes, close code)."""
    msgs: list[dict[str, Any]] = []
    audio = bytearray()
    while True:
        m = ws.receive()
        if m["type"] == "websocket.close":
            return msgs, bytes(audio), m.get("code")
        if m.get("bytes") is not None:
            audio += m["bytes"]
        elif m.get("text") is not None:
            msgs.append(json.loads(m["text"]))
