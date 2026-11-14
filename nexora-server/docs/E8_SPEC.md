# E8: admin dashboard (spec and results)

Phase E8 of `ENTERPRISE_PLAN.md`, built 2026-11-14 on the user's instruction to build the
remaining phases in order. Acceptance: a customer admin manages keys and sees usage without
the API.

## What it is

A web dashboard served by the server itself at **`/dashboard/`**: one HTML page, one
stylesheet and one script module (`src/nexora_server/dashboard/static/`). No build step, no
framework, no third-party scripts or CDNs.

| Page | Shows / does |
| --- | --- |
| Overview | Minutes this month, quota use (meter), sessions in the last 30 days, concurrency limit, a per-day minutes chart (all 30 days, zero where no calls), relay allowlist |
| API keys | List (name, prefix, scopes, created, last used), create (name + scopes; the secret is shown once with a copy button), revoke (with confirmation) |
| Profiles | List, create, edit, delete. Form fields for the common audio and turn settings (noise engine, echo cancellation, speech guard, background talker gate, Smart Turn, transcript cue, wait times); other settings as JSON. The server validates |
| Sessions | The last 100 calls: start, mode, duration, status and close reason, SNR, lost audio %, clipping %, turn count, engine |
| Audit log | The last 200 admin actions |
| Organizations | Super-admin only: list, create (shows the first admin key once), edit limits, quota, relay allowlist, suspend; pick an organization to manage it |

## Sign-in and security

- Sign in with an API key that has the `admin` scope (or the super-admin key). The key is
  kept in `sessionStorage` (this tab only, gone when it closes), never `localStorage` or a
  cookie. E9 adds single sign-on (OIDC) with an HttpOnly session cookie.
- New endpoint `GET /v1/me`: who the caller is (actor, organization, scopes).
- Served with a strict Content-Security-Policy (`default-src 'none'; script-src 'self';
  style-src 'self'; connect-src 'self'; frame-ancestors 'none'`), `X-Frame-Options: DENY`,
  `nosniff`, `no-referrer`, `no-store`.
- All data from the API is rendered with `textContent`, never parsed as HTML (an
  organization named `Acme <b>Calls</b>` shows exactly that). The static route serves a
  fixed list of files (no path traversal).

## Tests (`tests/test_dashboard.py`)

- Headers, static files, 404 for anything else, `/v1/me`, and every `/v1/...` path the
  script calls exists in the OpenAPI schema.
- **A real browser run**: headless Chrome over the DevTools protocol against a live server.
  It signs in, checks the overview (escaped name, quota, 30-day chart), creates a key
  (secret shown, works against the API), revokes it (rejected afterwards), creates a
  profile with echo cancellation (stored correctly), opens sessions and audit, signs out
  (tab storage cleared), and requires **no script errors and no CSP violations**. It runs
  in CI (Chrome is on GitHub's Ubuntu runners) and saves screenshots.

The browser test found a real bug before release: a closing dialog's late `close` event
reached the next dialog and blanked a newly created API key before it could be copied.
Each dialog is now its own element.

## Not covered (OPEN_ISSUES.md)

No accessibility audit beyond semantic HTML and labels; no mobile layout pass; English only.
