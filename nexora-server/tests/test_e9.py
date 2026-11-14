"""E9: metered billing (simulated Stripe), single sign-on (simulated OIDC provider) and
audit / usage exports."""

from __future__ import annotations

import base64
import hashlib
import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient

from nexora_server.app import create_app
from nexora_server.billing import BillingError, StripeMeter, report_usage
from nexora_server.db import Organization, SessionRecord
from tests.conftest import admin, bearer, make_settings, new_org

T0 = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)  # a Monday, on the hour


# -- billing -----------------------------------------------------------------------------


class FakeMeter:
    def __init__(self, fail_first: int = 0) -> None:
        self.events: list[dict[str, Any]] = []
        self.fail = fail_first

    def send(self, *, customer: str, value: int, at: datetime, identifier: str) -> None:
        if self.fail:
            self.fail -= 1
            raise BillingError("stripe 500: try again")
        self.events.append({"customer": customer, "value": value, "at": at, "id": identifier})


def _org_with_calls(client: Any, calls: list[tuple[timedelta, float]]) -> str:
    org_id, _ = new_org(client)
    db = client.app.state.db
    with db.session() as s:
        org = s.get(Organization, org_id)
        org.stripe_customer_id = "cus_TEST123"
        org.created_at = T0
        for ends_after, secs in calls:
            end = T0 + ends_after
            s.add(
                SessionRecord(
                    org_id=org_id,
                    mode="process",
                    status="ended",
                    audio_seconds=secs,
                    started_at=end - timedelta(seconds=secs),
                    ended_at=end,
                )
            )
    return org_id


CALLS = [  # (ends this long after T0, audio seconds): fractions on purpose
    (timedelta(minutes=10), 61.4),
    (timedelta(minutes=50), 30.3),
    (timedelta(hours=1, minutes=5), 0.4),  # alone it would round to 0
    (timedelta(hours=2, minutes=59), 600.45),
    (timedelta(hours=4, minutes=1), 12.2),
]


def test_invoice_matches_recorded_audio(client: Any) -> None:
    _org_with_calls(client, CALLS)
    meter = FakeMeter()
    res = report_usage(client.app.state.db, meter, now=T0 + timedelta(hours=5, minutes=6))
    recorded = sum(s for _, s in CALLS)
    assert sum(e["value"] for e in meter.events) == round(recorded)  # to the second
    assert len({e["id"] for e in meter.events}) == len(meter.events) == res.sent
    assert all(e["customer"] == "cus_TEST123" for e in meter.events)
    # hour 3 (no calls ended) is recorded as empty and not sent
    assert res.empty >= 1 and res.failed == 0
    # running again (or on another replica) sends nothing more
    again = report_usage(client.app.state.db, meter, now=T0 + timedelta(hours=5, minutes=30))
    assert again.sent == 0 and sum(e["value"] for e in meter.events) == round(recorded)


def test_open_hour_is_not_reported_until_closed(client: Any) -> None:
    _org_with_calls(client, [(timedelta(minutes=58), 100.0)])
    meter = FakeMeter()
    report_usage(client.app.state.db, meter, now=T0 + timedelta(minutes=59))
    assert meter.events == []
    report_usage(client.app.state.db, meter, now=T0 + timedelta(hours=1, minutes=2))  # grace
    assert meter.events == []
    report_usage(client.app.state.db, meter, now=T0 + timedelta(hours=1, minutes=6))
    assert [e["value"] for e in meter.events] == [100]


def test_failed_hours_are_retried(client: Any) -> None:
    _org_with_calls(client, CALLS)
    meter = FakeMeter(fail_first=2)
    first = report_usage(client.app.state.db, meter, now=T0 + timedelta(hours=5, minutes=6))
    assert first.failed == 2
    r = client.get(
        "/v1/billing/reports", headers=admin(), params={"org_id": first and _org(client)}
    )
    assert {x["status"] for x in r.json()} == {"sent", "failed"}
    second = report_usage(client.app.state.db, meter, now=T0 + timedelta(hours=5, minutes=20))
    assert second.sent == 2 and second.failed == 0
    assert sum(e["value"] for e in meter.events) == round(sum(s for _, s in CALLS))


def _org(client: Any) -> str:
    with client.app.state.db.session() as s:
        from sqlalchemy import select

        return str(
            s.scalar(select(Organization.id).where(Organization.stripe_customer_id.is_not(None)))
        )


def test_stripe_meter_request() -> None:
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        if b"cus_BAD" in req.content:
            return httpx.Response(400, json={"error": {"message": "No such customer"}})
        return httpx.Response(200, json={"object": "billing.meter_event"})

    http = httpx.Client(base_url="https://api.stripe.com", transport=httpx.MockTransport(handler))
    m = StripeMeter("sk_test_123", http=http)
    m.send(customer="cus_A", value=42, at=T0, identifier="nexora-org-20261102T09")
    req = seen[0]
    assert req.url.path == "/v1/billing/meter_events"
    assert req.headers["authorization"] == "Bearer sk_test_123"
    assert req.headers["idempotency-key"] == "nexora-org-20261102T09"
    form = parse_qs(req.content.decode())
    assert form["event_name"] == ["nexora_audio_seconds"]
    assert form["payload[stripe_customer_id]"] == ["cus_A"] and form["payload[value]"] == ["42"]
    assert form["timestamp"] == [str(int(T0.timestamp()))]
    with pytest.raises(BillingError, match="No such customer"):
        m.send(customer="cus_BAD", value=1, at=T0, identifier="x")


def test_stripe_customer_id_is_validated(client: Any) -> None:
    org_id, key = new_org(client)
    ok = client.patch(
        f"/v1/orgs/{org_id}", json={"stripe_customer_id": "cus_Abc123"}, headers=admin()
    )
    assert ok.status_code == 200 and ok.json()["stripe_customer_id"] == "cus_Abc123"
    bad = client.patch(f"/v1/orgs/{org_id}", json={"stripe_customer_id": "nope"}, headers=admin())
    assert bad.status_code == 422
    # customers cannot change their own billing link
    assert (
        client.patch(
            f"/v1/orgs/{org_id}", json={"stripe_customer_id": "cus_X1"}, headers=bearer(key)
        ).status_code
        == 403
    )


# -- exports -----------------------------------------------------------------------------


def test_audit_and_session_exports(client: Any) -> None:
    import csv
    import io

    org_id, key = new_org(client)
    client.post(
        "/v1/keys",
        json={"name": '=HYPERLINK("http://evil")', "scopes": ["stream"]},
        headers=bearer(key),
    )
    with client.app.state.db.session() as s:
        now = datetime.now(UTC)
        s.add(
            SessionRecord(
                org_id=org_id,
                mode="process",
                status="ended",
                audio_seconds=12.5,
                started_at=now - timedelta(minutes=1),
                ended_at=now,
                close_reason="+cmd|calc",
                quality={"snr_db": 20.1},
            )
        )
    r = client.get("/v1/audit/export", headers=bearer(key))
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert {"org.create", "key.create"} <= {x["action"] for x in rows}
    j = client.get("/v1/audit/export", params={"format": "jsonl"}, headers=bearer(key))
    assert all(json.loads(line)["id"] for line in j.text.splitlines())
    sess = client.get("/v1/sessions/export", headers=bearer(key))
    srow = next(csv.DictReader(io.StringIO(sess.text)))
    assert float(srow["audio_seconds"]) == 12.5
    assert srow["close_reason"] == "'+cmd|calc"  # spreadsheet formula defused
    assert json.loads(srow["quality"]) == {"snr_db": 20.1}
    too_long = {"start": "2024-01-01T00:00:00Z", "end": "2026-01-01T00:00:00Z"}
    assert client.get("/v1/audit/export", params=too_long, headers=bearer(key)).status_code == 422
    stream_only = client.post("/v1/keys", json={"scopes": ["stream"]}, headers=bearer(key)).json()
    assert client.get("/v1/audit/export", headers=bearer(stream_only["api_key"])).status_code == 403


# -- single sign-on ----------------------------------------------------------------------

ISSUER = "https://idp.example.com"


class FakeIdP:
    """Discovery, JWKS and a token endpoint that checks PKCE, behind httpx.MockTransport."""

    def __init__(self) -> None:
        from cryptography.hazmat.primitives.asymmetric import rsa

        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        self.jwks = {"keys": [{**jwk, "kid": "k1", "use": "sig", "alg": "RS256"}]}
        self.challenge = ""
        self.claims: dict[str, Any] = {}
        self.sign_with = self.key

    def handler(self, req: httpx.Request) -> httpx.Response:
        if req.url.path == "/.well-known/openid-configuration":
            return httpx.Response(
                200,
                json={
                    "issuer": ISSUER,
                    "authorization_endpoint": f"{ISSUER}/authorize",
                    "token_endpoint": f"{ISSUER}/token",
                    "jwks_uri": f"{ISSUER}/jwks",
                },
            )
        if req.url.path == "/jwks":
            return httpx.Response(200, json=self.jwks)
        if req.url.path == "/token":
            form = parse_qs(req.content.decode())
            verifier = form["code_verifier"][0]
            digest = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            if digest.rstrip(b"=").decode() != self.challenge or form["code"] != ["good-code"]:
                return httpx.Response(400, json={"error": "invalid_grant"})
            token = jwt.encode(
                self.claims, self.sign_with, algorithm="RS256", headers={"kid": "k1"}
            )
            return httpx.Response(200, json={"id_token": token, "token_type": "Bearer"})
        return httpx.Response(404)


@pytest.fixture
def sso(tmp_path: Path) -> Any:
    from nexora_server.sso import OidcProvider

    settings = make_settings(
        tmp_path,
        oidc_issuer=ISSUER,
        oidc_client_id="nexora-dash",
        oidc_client_secret="s3cret",
        oidc_redirect_url="http://testserver/auth/oidc/callback",
        cookie_secure=False,
        sso_superadmin_emails=["root@nexora.example"],
    )
    idp = FakeIdP()
    app = create_app(settings, prewarm=False)
    app.state.oidc = OidcProvider(
        settings, http=httpx.Client(transport=httpx.MockTransport(idp.handler))
    )
    with TestClient(app) as c:
        yield c, idp


def _sign_in(c: TestClient, idp: FakeIdP, email: str, **overrides: Any) -> httpx.Response:
    c.cookies.clear()
    r = c.get("/auth/oidc/login", follow_redirects=False)
    assert r.status_code == 302
    q = parse_qs(urlparse(r.headers["location"]).query)
    assert q["code_challenge_method"] == ["S256"] and q["client_id"] == ["nexora-dash"]
    idp.challenge = q["code_challenge"][0]
    now = int(time.time())
    idp.claims = {
        "iss": ISSUER,
        "aud": "nexora-dash",
        "sub": "u-1",
        "iat": now,
        "exp": now + 300,
        "nonce": q["nonce"][0],
        "email": email,
        "email_verified": True,
    }
    state = overrides.pop("state", q["state"][0])
    idp.claims.update(overrides)
    return c.get(f"/auth/oidc/callback?code=good-code&state={state}", follow_redirects=False)


CSRF = {"X-Nexora-CSRF": "1"}


def test_sso_sign_in_as_org_member(sso: Any) -> None:
    c, idp = sso
    org_id, key = new_org(c)
    assert c.get("/auth/oidc/status").json() == {"enabled": True}
    c.post("/v1/sso/members", json={"email": "Alice@Acme.example"}, headers=bearer(key))
    r = _sign_in(c, idp, "alice@acme.example")
    assert r.status_code == 302 and r.headers["location"] == "/dashboard/"
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    me = c.get("/v1/me", headers=CSRF).json()
    assert me["org_id"] == org_id and me["actor"] == "sso:alice@acme.example"
    assert "admin" in me["scopes"] and "stream" not in me["scopes"]
    # the cookie alone (no CSRF header, as a forged cross-site request would be) is refused
    assert c.get("/v1/me").status_code == 401
    assert c.post("/v1/keys", json={"scopes": ["stream"]}).status_code == 401
    assert c.post("/v1/keys", json={"scopes": ["stream"]}, headers=CSRF).status_code == 201
    # removing the member ends the session at once
    mid = c.get("/v1/sso/members", headers=bearer(key)).json()[0]["id"]
    c.delete(f"/v1/sso/members/{mid}", headers=bearer(key))
    assert c.get("/v1/me", headers=CSRF).status_code == 401


def test_sso_superadmin_and_logout(sso: Any) -> None:
    c, idp = sso
    assert _sign_in(c, idp, "root@nexora.example").status_code == 302
    me = c.get("/v1/me", headers=CSRF).json()
    assert me["superadmin"] is True and me["actor"] == "superadmin:sso:root@nexora.example"
    assert c.get("/v1/orgs", headers=CSRF).status_code == 200
    assert c.post("/auth/logout").status_code == 204
    assert c.get("/v1/me", headers=CSRF).status_code == 401


@pytest.mark.parametrize(
    ("overrides", "status"),
    [
        ({"state": "forged"}, 400),
        ({"nonce": "replayed"}, 401),
        ({"aud": "someone-else"}, 401),
        ({"iss": "https://evil.example"}, 401),
        ({"exp": int(time.time()) - 3600}, 401),
        ({"email_verified": False}, 403),
        ({"email": "mallory@acme.example"}, 403),  # not a member
        ({"sign_with_other_key": True}, 401),
    ],
)
def test_sso_rejections(sso: Any, overrides: dict[str, Any], status: int) -> None:
    c, idp = sso
    _, key = new_org(c)
    c.post("/v1/sso/members", json={"email": "alice@acme.example"}, headers=bearer(key))
    idp.sign_with = idp.other if overrides.pop("sign_with_other_key", False) else idp.key
    email = overrides.pop("email", "alice@acme.example")
    r = _sign_in(c, idp, email, **overrides)
    assert r.status_code == status, r.text
    assert c.get("/v1/me", headers=CSRF).status_code == 401


def test_sso_off_by_default(client: Any) -> None:
    assert client.get("/auth/oidc/status").json() == {"enabled": False}
    assert client.get("/auth/oidc/login", follow_redirects=False).status_code == 404


def test_members_are_scoped_to_the_org(client: Any) -> None:
    _, key_a = new_org(client, name="A")
    _, key_b = new_org(client, name="B")
    m = client.post("/v1/sso/members", json={"email": "x@a.example"}, headers=bearer(key_a)).json()
    assert client.delete(f"/v1/sso/members/{m['id']}", headers=bearer(key_b)).status_code == 404
    assert client.get("/v1/sso/members", headers=bearer(key_b)).json() == []
    dup = client.post("/v1/sso/members", json={"email": "X@A.example"}, headers=bearer(key_a))
    assert dup.status_code == 409
