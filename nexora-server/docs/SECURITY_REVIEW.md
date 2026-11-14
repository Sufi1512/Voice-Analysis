# Security review (E10, 2026-11-14)

Scope: `nexora-server` (REST API, WebSocket streaming and relay, dashboard, SSO, billing),
`nexora-client`, `nexora-audio` (the server's processing engine), Kubernetes manifests.
Method: automated scans (bandit static analysis, pip-audit against known vulnerabilities in
all 96 installed dependencies), a manual review of every authentication, authorization and
input path, and chaos tests. This is an internal review by the engineering side, **not an
independent penetration test** (see "Not done").

## Results

| Check | Result |
| --- | --- |
| pip-audit (96 packages, OSV/PyPI advisories) | No known vulnerabilities |
| bandit, high severity | None |
| bandit, medium | 2: binding to 0.0.0.0 (intended: container listens on all interfaces behind the load balancer) |
| bandit, low | `assert` in security paths (fixed, now enforced by a test), one false positive (a token audience string taken for a password) |

## Findings and fixes

| ID | Severity | Finding | Status |
| --- | --- | --- | --- |
| S-1 | Medium | **Relay DNS rebinding (SaaS mode).** The agent host was resolved and checked for internal addresses, then resolved again by the WebSocket library when connecting. An allowlisted domain whose DNS changes in between could reach internal addresses (e.g. cloud metadata at 169.254.169.254). | **Fixed**: resolve once, refuse if any address is internal (IPv4-mapped IPv6 included), connect a socket to the vetted address and do TLS with the original host name. Tests: internal ranges refused; a resolver that changes its answer after the first lookup is never asked twice. |
| S-2 | Medium | **Oversized WebSocket frames.** Uvicorn accepted 16 MB frames; the 256 KB message limit was applied only after a frame was fully buffered, so many large frames could use a lot of memory. | **Fixed**: `ws_max_size` = 2 x `NEXORA_MAX_MESSAGE_BYTES` (control messages carry base64 audio). Test checks the server configuration. |
| S-3 | Medium | **Connection floods degrade live calls.** In the load test, callers retrying a full server in a tight loop (7,485 attempts in 40 s) pushed the 4 admitted calls to 12 s latency: each refused attempt still cost a database lookup and key check. | **Mitigated**: a full, overloaded or draining instance now refuses before authentication (same test: 56 refusals, admitted calls p50 7.9 ms, p99 111 ms). The client backs off. **Open**: per-IP/per-key connection rate limiting belongs at the edge (I-035). |
| S-4 | Low | Logout endpoint could be triggered from another site (log-out CSRF). | **Fixed**: requires the `X-Nexora-CSRF` header. |
| S-5 | Low | `assert` used for an organization-scoping check and the relay target check; Python removes asserts under `-O`. | **Fixed**: explicit checks; a test fails if any `assert` appears in server code. |
| S-6 | Low | API responses (keys, tokens, usage) had no `Cache-Control: no-store` or `nosniff`. | **Fixed** for `/v1/*` and `/auth/*`. |
| S-7 | Low | End-of-call cleanup could be skipped when the caller vanished or the database failed: the session stayed `active` (not billed) and its audio session was not returned. | **Fixed** (chaos tests): each cleanup step independent and shielded from cancellation; failures to record are counted (`nexora_session_record_errors_total`). |
| S-8 | Info | Without `NEXORA_SECRET_KEY` the server starts with a random key (warning). Tokens and API-key hashes then break on restart and across instances. | Accepted: documented as required; Kubernetes reads it from a Secret. |
| S-9 | Info | Browser clients may pass a session token in the URL (`?token=`), which proxies can log. | Accepted: tokens live 5 minutes and are scoped to one organization; prefer the header. |

## Reviewed and found sound

- **API keys**: 256-bit random, stored as HMAC-SHA256 with a server pepper, compared in constant
  time, prefix lookup, revocable, organization must be active. Super-admin key compared in
  constant time.
- **Session tokens**: HS256 with audience, expiry and organization; relay targets re-checked.
- **SSO (E9)**: PKCE S256, state and nonce in a signed short-lived cookie, ID token signature from
  the provider's JWKS (RSA/EC only, key rotation), issuer, audience, expiry, nonce, verified
  email; session cookie HttpOnly + SameSite=Strict + Secure and usable only with the CSRF header;
  membership re-checked per request. Eight rejection cases tested.
- **Authorization**: every route goes through a scope check and `org_for` (an organization key
  cannot name another organization; tested), super-admin only routes separate.
- **Dashboard**: strict CSP (no inline script, no third parties), frame-deny, every value rendered
  as text, fixed static file list (no traversal), key in tab storage only.
- **Exports**: CSV formula injection defused; size-limited ranges; exports are audited.
- **Relay policy**: ws/wss only, wss in SaaS, no credentials in URLs, host allowlist set only by
  the platform admin, internal addresses refused (now without a rebinding window).
- **Billing**: idempotent per organization-hour, provider idempotency keys; Stripe key from the
  environment only.
- **Containers**: non-root user, read-only root file system, all capabilities dropped,
  seccomp RuntimeDefault, no privilege escalation; secrets only from a Kubernetes Secret.
- **Logs**: no audio, no keys; key prefixes only.

## Not done (open, see `OPEN_ISSUES.md`)

- An **independent penetration test** (I-036): the acceptance criterion says "no open
  high-severity findings"; this review found none open, but it was not independent.
- Edge rate limiting / WAF for connection floods (I-035).
- Load and soak at production scale (hundreds of sessions, 72 hours): see `E10_RESULTS.md`.
