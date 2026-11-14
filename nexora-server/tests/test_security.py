"""E10 security review fixes: relay DNS rebinding, frame size, API headers, no asserts."""

from __future__ import annotations

import socket
from typing import Any

import pytest

from nexora_server import relay_policy
from nexora_server.relay_policy import RelayTargetError, open_vetted_socket
from tests.conftest import bearer, new_org


def _resolver(*addrs: str) -> Any:
    def fake(host: str, port: int, type: int = 0) -> list[Any]:
        fam = socket.AF_INET6 if ":" in addrs[0] else socket.AF_INET
        return [(fam, socket.SOCK_STREAM, 6, "", (a, port)) for a in addrs]

    return fake


@pytest.mark.parametrize(
    "addr", ["10.0.0.5", "127.0.0.1", "169.254.169.254", "::1", "::ffff:127.0.0.1", "fd00::1"]
)
def test_relay_refuses_internal_addresses(monkeypatch: Any, addr: str) -> None:
    monkeypatch.setattr(relay_policy.socket, "getaddrinfo", _resolver(addr))
    with pytest.raises(RelayTargetError, match="non-public"):
        open_vetted_socket("wss://agent.example.com/ws", "saas")


def test_relay_connects_to_the_address_it_checked(monkeypatch: Any) -> None:
    """DNS rebinding: the socket goes to the vetted IP; the host is never looked up again."""
    lookups: list[str] = []
    connected: list[tuple[str, int]] = []

    def resolver(host: str, port: int, type: int = 0) -> list[Any]:
        lookups.append(host)
        ip = "93.184.216.34" if len(lookups) == 1 else "169.254.169.254"  # rebinds later
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]

    def connect(addr: tuple[str, int], timeout: float = 0) -> Any:
        connected.append(addr)
        return object()

    monkeypatch.setattr(relay_policy.socket, "getaddrinfo", resolver)
    monkeypatch.setattr(relay_policy.socket, "create_connection", connect)
    assert open_vetted_socket("wss://agent.example.com:8443/ws", "saas") is not None
    assert lookups == ["agent.example.com"] and connected == [("93.184.216.34", 8443)]
    assert open_vetted_socket("ws://agent.local/ws", "self_hosted") is None


def test_api_responses_are_not_cached_or_sniffed(client: Any) -> None:
    _, key = new_org(client)
    r = client.get("/v1/me", headers=bearer(key))
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["x-content-type-options"] == "nosniff"


def test_websocket_frames_are_capped_at_the_protocol_layer(monkeypatch: Any) -> None:
    import sys

    from nexora_server import __main__ as main_mod

    seen: dict[str, Any] = {}

    class FakeServer:
        def __init__(self, config: Any, app: Any, drain: float) -> None:
            seen["config"], seen["app"] = config, app

        def run(self) -> None:
            pass

    monkeypatch.setattr(main_mod, "_server_class", lambda: FakeServer)
    monkeypatch.setattr(sys, "argv", ["nexora-server", "--no-prewarm"])
    monkeypatch.setenv("NEXORA_DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("NEXORA_SECRET_KEY", "x" * 40)
    monkeypatch.setenv("NEXORA_MAX_MESSAGE_BYTES", "65536")
    main_mod.main()
    assert seen["config"].ws_max_size == 2 * 65536  # not uvicorn's 16 MB default


def test_no_asserts_guard_security_checks() -> None:
    """``python -O`` strips asserts; access checks must not depend on them."""
    import ast
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "src" / "nexora_server"
    offenders = []
    for f in src.rglob("*.py"):
        if "migrations" in f.parts:
            continue
        for node in ast.walk(ast.parse(f.read_text())):
            if isinstance(node, ast.Assert):
                offenders.append(f"{f.name}:{node.lineno}")
    assert offenders == []


def test_overloaded_instance_refuses_new_calls(client: Any) -> None:
    """When audio jobs queue up (CPU saturated), new calls get 1013 instead of slowing
    everyone down; readiness turns red so the load balancer stops sending calls."""
    mgr = client.app.state.manager
    _, key = new_org(client)
    mgr.overload_queue = -1  # any queue depth counts as overloaded
    try:
        assert client.get("/readyz").status_code == 503
        with client.websocket_connect("/v1/stream", headers=bearer(key)) as ws:
            err = ws.receive_json()
        assert err["code"] == 1013 and "overloaded" in err["message"]
        assert 'reason="overloaded"' in client.get("/metrics").text
    finally:
        mgr.overload_queue = 2 * 2
    assert client.get("/readyz").status_code == 200
