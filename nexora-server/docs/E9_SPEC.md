# E9: billing, single sign-on, audit export (spec and results)

Phase E9 of `ENTERPRISE_PLAN.md`, built 2026-11-14 on the user's instruction to build the
remaining phases in order. Acceptance: invoice usage matches recorded audio seconds.

## 1. Metered billing (Stripe billing meters) - `billing.py`

- Set `NEXORA_STRIPE_API_KEY` (and optionally `NEXORA_STRIPE_METER_EVENT`, default
  `nexora_audio_seconds`); link an organization with `PATCH /v1/orgs/{id}`
  `{"stripe_customer_id": "cus_..."}` (super-admin only).
- Every 5 minutes (`NEXORA_BILLING_INTERVAL_S`) each closed hour (5-minute grace) becomes one
  Stripe meter event (`POST /v1/billing/meter_events`): the audio seconds of sessions that
  **ended** in that hour, as whole seconds.
- **Invoice = recorded audio, to the second**: rounding is carried over, so the seconds
  reported so far always equal the recorded seconds so far, rounded.
- **Never billed twice**: each hour is first written to `usage_reports` (unique per
  organization and hour; another replica that tries the same hour does nothing), then sent
  with a unique `identifier` and `Idempotency-Key`. Failed hours are retried next run.
- `GET /v1/billing/reports`, the dashboard's Billing page, and `nexora-server
  billing-report` (one run, for a CronJob instead of the in-process loop).
- Stripe side (one-off setup): a billing meter with event name `nexora_audio_seconds`,
  aggregation `sum`, and a metered price on it (per minute: `transform_quantity[divide_by]=60`).

Usage pages, the monthly quota and billing all count a call when it **ends** (only then are its
seconds final), so a call crossing midnight shows on the day it ended everywhere (I-029, fixed
2026-11-14). The session export lists calls by start time.

Lost calls (I-030, fixed 2026-11-14): every running call saves its audio seconds and a
heartbeat every `NEXORA_CHECKPOINT_INTERVAL_S` (30 s). If the server running it dies, a
sweeper on every server closes it after `NEXORA_STALE_SESSION_AFTER_S` (120 s) as `failed`,
ending at its last heartbeat with the seconds saved then. Reports are running totals, so a
call back-dated into an hour that was already reported is billed in the next report
(`nexora_sessions_swept_total` counts them).

## 2. Single sign-on for the dashboard (OpenID Connect) - `sso.py`

- Settings: `NEXORA_OIDC_ISSUER`, `NEXORA_OIDC_CLIENT_ID`, `NEXORA_OIDC_CLIENT_SECRET`,
  `NEXORA_OIDC_REDIRECT_URL` (`https://<host>/auth/oidc/callback`),
  `NEXORA_SSO_SUPERADMIN_EMAILS`, `NEXORA_SSO_SESSION_TTL_S` (8 h).
- Authorization-code flow with PKCE (S256), `state` and `nonce` in a 10-minute signed
  HttpOnly cookie. The ID token is verified against the provider's JWKS (RS256/ES256/PS256,
  key rotation handled), issuer, audience, expiry and nonce. The email must be verified.
- Who may sign in: emails added by an organization admin (`/v1/sso/members`, dashboard
  **Team** page; roles `admin` or `viewer`), plus the configured super-admin emails.
- The session is a signed cookie, `HttpOnly`, `SameSite=Strict`, `Secure`. Requests that use
  it must send `X-Nexora-CSRF: 1` (the dashboard does; a forged cross-site request cannot).
  Membership is re-checked on every request: removing someone signs them out at once.
- Works with Google Workspace, Microsoft Entra ID, Okta, Auth0, Keycloak (standard
  discovery). Not tested against a real provider here.

## 3. Audit and usage export

- `GET /v1/audit/export` (admin) and `GET /v1/sessions/export` (usage:read), `format=csv`
  or `jsonl`, `start`/`end` (default the last 31 days, at most 400 days). Streamed, as a
  download. CSV cells that a spreadsheet would run as a formula (`= + - @`) are prefixed with
  `'`. Audit exports are themselves audited. Dashboard: "Export" buttons on Audit log and
  Sessions.

## Database

Migration `0002`: `organizations.stripe_customer_id`, `usage_reports`, `sso_members`. A
database made by `create_all` is stamped with the revision it matches.

## Tests (`tests/test_e9.py`, `tests/test_dashboard.py`)

- Billing against a simulated meter: totals equal recorded seconds (fractions across hours),
  unique identifiers, re-runs send nothing, open hours wait for the grace period, failed hours
  are retried; the real Stripe request format (form fields, auth, idempotency) against a mock
  transport; customer ID validation; customers cannot change their own billing link.
- SSO against a simulated provider (real RSA keys, PKCE checked by the provider): member
  sign-in, cookie flags, CSRF header required, removal ends the session, super-admin,
  logout; rejected: forged state, wrong nonce, wrong audience, wrong issuer, expired token,
  unverified email, non-member, token signed by another key.
- Exports: CSV/JSONL content, formula defusing, range limit, scopes. The browser test adds a
  team member, opens Billing and downloads a real CSV export.

The tests found a routing bug: `/v1/sessions/export` was taken as the session with ID
`export`. Fixed by route order.
