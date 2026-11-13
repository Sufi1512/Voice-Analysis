"""REST API: tenants, keys, scopes, profiles, tokens, audit."""

from __future__ import annotations

from typing import Any

import pytest

from nexora_server.relay_policy import RelayTargetError, check_relay_target
from nexora_server.security import generate_api_key, key_prefix, verify_key
from tests.conftest import admin, bearer, new_org


def test_health_and_auth_required(client: Any) -> None:
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").status_code == 200
    assert client.get("/v1/keys").status_code == 401
    assert client.get("/v1/keys", headers=bearer("nx_bogus")).status_code == 401


def test_api_key_format_and_hashing() -> None:
    k = generate_api_key("pepper")
    assert k.plaintext.startswith("nx_") and key_prefix(k.plaintext) == k.prefix
    assert verify_key(k.plaintext, k.key_hash, "pepper")
    assert not verify_key(k.plaintext, k.key_hash, "other-pepper")
    assert k.plaintext not in k.key_hash


def test_org_lifecycle_and_isolation(client: Any) -> None:
    org_a, key_a = new_org(client, max_concurrent_sessions=3)
    org_b, _ = new_org(client)
    assert client.get(f"/v1/orgs/{org_a}", headers=bearer(key_a)).json()["id"] == org_a
    assert client.get(f"/v1/orgs/{org_b}", headers=bearer(key_a)).status_code == 403
    assert client.get("/v1/orgs", headers=bearer(key_a)).status_code == 403  # super-admin only
    assert len(client.get("/v1/orgs", headers=admin()).json()) == 2
    r = client.patch(f"/v1/orgs/{org_a}", json={"active": False}, headers=admin())
    assert r.json()["active"] is False
    assert client.get("/v1/keys", headers=bearer(key_a)).status_code == 401  # inactive org


def test_keys_scopes_and_revocation(client: Any) -> None:
    _, admin_key = new_org(client)
    r = client.post(
        "/v1/keys", json={"name": "agent", "scopes": ["stream"]}, headers=bearer(admin_key)
    )
    assert r.status_code == 201
    stream_key, key_id = r.json()["api_key"], r.json()["key"]["id"]
    listed = client.get("/v1/keys", headers=bearer(admin_key)).json()
    assert {k["id"] for k in listed} >= {key_id}
    assert all("hash" not in k and "api_key" not in k for k in listed)  # secrets never listed
    # a stream-only key cannot administer
    assert (
        client.post("/v1/profiles", json={"name": "x"}, headers=bearer(stream_key)).status_code
        == 403
    )
    assert client.post("/v1/session-tokens", json={}, headers=bearer(stream_key)).status_code == 201
    assert client.delete(f"/v1/keys/{key_id}", headers=bearer(admin_key)).json()["revoked_at"]
    assert client.post("/v1/session-tokens", json={}, headers=bearer(stream_key)).status_code == 401
    bad = client.post("/v1/keys", json={"scopes": ["root"]}, headers=bearer(admin_key))
    assert bad.status_code == 422


def test_profiles_validation_and_default(client: Any) -> None:
    _, key = new_org(client)
    h = bearer(key)
    ok = client.post(
        "/v1/profiles",
        json={
            "name": "telephony",
            "audio_settings": {"noise_backend": "rnnoise", "clarity_db": 4},
            "turn_settings": {"end_of_turn_ms": 900},
            "is_default": True,
        },
        headers=h,
    )
    assert ok.status_code == 201, ok.text
    assert client.post("/v1/profiles", json={"name": "telephony"}, headers=h).status_code == 409
    bad = client.post(
        "/v1/profiles", json={"name": "bad", "audio_settings": {"clarity_db": 99}}, headers=h
    )
    assert bad.status_code == 422
    owned = client.post(
        "/v1/profiles", json={"name": "o", "audio_settings": {"sample_rate": 8000}}, headers=h
    )
    assert owned.status_code == 422 and "per stream" in owned.text
    second = client.post("/v1/profiles", json={"name": "web", "is_default": True}, headers=h).json()
    profiles = {p["name"]: p for p in client.get("/v1/profiles", headers=h).json()}
    assert profiles["web"]["is_default"] and not profiles["telephony"]["is_default"]
    patched = client.patch(f"/v1/profiles/{second['id']}", json={"disable_turns": True}, headers=h)
    assert patched.json()["turn_settings"] is None
    assert client.delete(f"/v1/profiles/{second['id']}", headers=h).status_code == 204


def test_session_tokens_and_relay_allowlist(client: Any) -> None:
    _, key = new_org(client, relay_allowlist=["agent.example.com", "*.voice.example.org"])
    h = bearer(key)
    r = client.post("/v1/session-tokens", json={"mode": "process"}, headers=h)
    assert r.status_code == 201 and r.json()["token"].count(".") == 2
    assert client.post("/v1/session-tokens", json={"mode": "relay"}, headers=h).status_code == 422
    denied = client.post(
        "/v1/session-tokens",
        json={"mode": "relay", "relay_target": "ws://evil.example.net/x"},
        headers=h,
    )
    assert denied.status_code == 422 and "allowlist" in denied.text
    allowed = client.post(
        "/v1/session-tokens",
        json={"mode": "relay", "relay_target": "ws://eu.voice.example.org/a"},
        headers=h,
    )
    assert allowed.status_code == 201  # self-hosted mode: allowlist only


def test_audit_log(client: Any) -> None:
    _, key = new_org(client)
    client.post("/v1/keys", json={"scopes": ["stream"]}, headers=bearer(key))
    actions = [a["action"] for a in client.get("/v1/audit", headers=bearer(key)).json()]
    assert "org.create" in actions and "key.create" in actions


@pytest.mark.parametrize(
    "url,allow,msg",
    [
        ("http://agent.example.com", ["agent.example.com"], "ws://"),
        ("ws://agent.example.com", ["agent.example.com"], "wss://"),
        ("wss://agent.example.com", ["other.example.com"], "allowlist"),
        ("wss://user:pw@agent.example.com", ["agent.example.com"], "credentials"),
        ("wss://127.0.0.1:9000", ["127.0.0.1"], "non-public"),
        ("wss://localhost:9000", ["localhost"], "non-public"),
        ("wss://169.254.169.254/", ["169.254.169.254"], "non-public"),  # cloud metadata
    ],
)
def test_saas_relay_policy_blocks_unsafe_targets(url: str, allow: list[str], msg: str) -> None:
    with pytest.raises(RelayTargetError, match=msg):
        check_relay_target(url, allow, "saas")
