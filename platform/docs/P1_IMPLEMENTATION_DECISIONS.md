# P1 implementation decisions

Choices made while building P1 tickets that the spec leaves open. Same format as
`P0_IMPLEMENTATION_DECISIONS.md`. Each is covered by the ticket's tests.

| # | Ticket | Decision | Reason |
|---|---|---|---|
| D1 | C2 | Global tables (users, sessions, reset tokens, login throttle) have no row-level security and are read by `nexora_app`; `nexora_admin` (BYPASSRLS) is kept for tenant-table lookups before an organization is known (invitation tokens) and platform-owner actions. | The bypass role is never used where the app role suffices. |
| D2 | C4 | Audit writes for one organization are serialised with `pg_advisory_xact_lock(hashtext('audit:' \|\| org))`; the service sets `occurred_at` and it is inside the hash. | The app role cannot lock or change audit rows, so row locks are not available; a database default timestamp would not be known before hashing. |
| D3 | C4 | `record()` refuses details keys containing password, token, secret, code or otp. | Audit rows are permanent; secrets must never land there. |
| D4 | C5 | Cookies use the `__Host-` prefix (`__Host-nexora_session`, HttpOnly; `__Host-nexora_csrf`, readable by the portal). | Browsers then require Secure, Path=/ and no Domain, so a sibling subdomain cannot set or shadow them. |
| D5 | C5 | Double-submit CSRF applies to every unsafe `/v1/` request, login included; `GET /v1/auth/csrf` issues the token, and login rotates it. | Covers login CSRF without a separate mechanism. |
| D6 | C5 | Lockout counts failures for unknown emails too, and an unknown email spends one argon2 verification against a dummy hash. | Same response and timing for "no such user" and "wrong password", so emails cannot be enumerated. |
| D7 | C5 | A per-IP limit (100 failures a minute, 15-minute lock) runs alongside the per-email limit (10). **Deploy must set uvicorn `--forwarded-allow-ips` to the reverse proxy**, or every user shares the proxy's address. | Spec asks for per-IP and per-email limits; the IP limit is set high so an office NAT is not locked out. |
| D8 | C5 | Signing in revokes the session in the incoming cookie. | No session fixation and no stale sessions left behind. |
| D9 | C5 | Request time comes from `app.state.clock` (UTC), never from database `now()`, for session and throttle checks. | Tests move time precisely; one source of time per request. |

Known limit: anyone who knows an email can lock it for 15 minutes by failing 10 sign-ins. This is
inherent to the lockout the spec requires (AC-3); the generic error keeps it from revealing whether the
account exists.
