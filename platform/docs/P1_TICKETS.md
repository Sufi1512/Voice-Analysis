# P1 NEXORA Core: tickets

From `P1_SPEC.md` (approved 2026-11-14). Branch `platform/p1-core`. Backend first, then the portal.

| Ticket | Title | Depends on | Size |
|---|---|---|---|
| C1 | Core service skeleton, settings, health, test database harness, CI job | none | M |
| C2 | Schema and migrations with row-level security | C1 | M |
| C3 | Secrets: envelope encryption | C1 | S |
| C4 | Audit log with hash chain | C2 | S |
| C5 | Passwords, sessions, login, logout, logout everywhere, lockout, CSRF | C2 | M |
| C6 | Roles, permission catalogue, per-request authorization and RLS context | C5 | M |
| C7 | Platform owner bootstrap; platform creates organizations (with Production workspace) | C6, C4 | S |
| C8 | SMTP email; invitations (Viewer default, 7 days, single use); accept flow | C7 | M |
| C9 | Members: list, change role, remove; last owner protected; workspaces list/create | C8 | S |
| C10 | Password reset by email | C8 | S |
| C11 | TOTP MFA with recovery codes; required for owners and admins | C5 | M |
| C12 | Microsoft sign-in (OIDC) linking to invited accounts only | C8 | M |
| C13 | Self sign-up behind `NEXORA_SELF_SIGNUP` (off) | C8 | S |
| W1 | Portal shell: Next.js, Signal Room tokens, translation keys, RTL lint rules | C1 | M |
| W2 | Portal: sign-in, MFA setup and prompt, invitation acceptance, password reset | W1, C11 | M |
| W3 | Portal: platform admin, members and roles, workspaces, overview with health | W2, C9 | M |
| W4 | Docker Compose stack (Core, PostgreSQL, Redis, Mailpit, portal) and end-to-end tests | W3 | M |

## Coverage
| Spec criterion | Tickets |
|---|---|
| AC-1 organization isolation (API and RLS) | C2, C6 |
| AC-2 endpoint × role allow/deny table | C6 (+ every endpoint ticket adds its rows) |
| AC-3 accept, login, logout, logout everywhere, reset, SMTP, lockout | C5, C8, C10 |
| AC-4 Microsoft sign-in links only after confirmation | C12 |
| AC-4b MFA enforced for owners and admins, recovery codes single use | C11 |
| AC-4c self sign-up 404 when off | C13 |
| AC-4d invite defaults to Viewer | C8 |
| AC-5 invitations 7 days, single use | C8 |
| AC-6 last owner protected | C9 |
| AC-7 audit rows, hash chain, no update/delete | C4 |
| AC-8 migrations up and down | C2 |
| AC-9 portal end-to-end flow | W2, W3, W4 |
| AC-9b right-to-left ready | W1, W4 |
| AC-10 CI on Linux | C1, W1, W4 |

## Ticket notes (acceptance criteria are the spec's; tests are written first in each)
- **C1** `platform/services/core/` with uv, Python 3.13, FastAPI, pydantic-settings, structlog JSON logs.
  Tests: `/healthz` 200; `/readyz` 503 when the database is down, 200 when up; settings refuse to start without a session secret in production mode.
- **C2** Alembic, tables from DB doc §3.1, §3.2, §3.9 and `secrets` (§3.7). Every tenant table has `organization_id` and an RLS policy on `current_setting('nexora.org_id')`; the app connects as a non-owner role. Tests: up/down on an empty database; with org A set, rows of org B are invisible to SELECT, UPDATE and DELETE as the app role.
- **C3** AES-256-GCM data keys wrapped by a key-encryption key from settings (local key in development, a KMS adapter later). Tests: round trip; tampered ciphertext refused; wrong KEK refused; plaintext never in repr or logs.
- **C4** Append-only `audit_logs`, `prev_hash`/`hash` SHA-256 chain per organization; UPDATE/DELETE revoked from the app role. Tests: chain verifies; editing a row is refused; a forged row breaks verification.
- **C5** argon2id; server-side sessions (random 256-bit id, stored hashed, 12 h idle, 7 d absolute); cookie HttpOnly, Secure, SameSite=Lax; double-submit CSRF token on unsafe methods; 10 failures per minute per email → 15 min lock. Tests per behaviour, including revoked session and logout everywhere.
- **C6** Permission catalogue in code, seeded; the seven roles; FastAPI dependency `require(permission)`; transaction sets `nexora.org_id`; 404 for organizations the user is not in. Test: table-driven matrix generated from the catalogue and the route table.
- **C7** First platform owner from `NEXORA_BOOTSTRAP_OWNER_EMAIL` + one-time password file on first start; `POST /v1/platform/organizations` creates the organization, a Production workspace and the first owner's invitation.
- **C8** SMTP via aiosmtplib (host, port, STARTTLS/TLS, user, sender from settings); Mailpit in tests. Invitation token 256-bit, stored hashed, 7 days, single use; role default Viewer; scope organization or workspace.
- **C9** Organization owner/admin manage members; removing or demoting the last Organization owner is refused (409).
- **C10** Reset token 256-bit, hashed, 30 minutes, single use; all sessions revoked after reset; response is the same whether or not the email exists.
- **C11** TOTP (RFC 6238, 30 s, 6 digits, ±1 step), secret stored through C3; 10 recovery codes, hashed, single use; until set up, an owner/admin session can call only MFA setup and logout.
- **C12** Authorization code flow with PKCE against Microsoft Entra ID (`login.microsoftonline.com/{tenant}/v2.0`); tests run against a local fake OIDC provider; a Microsoft identity links only to an existing user whose invite or password confirms it; never creates a user.
- **C13** `NEXORA_SELF_SIGNUP=false` default → `POST /v1/auth/signup` 404; true → sign-up creates a user and, after verification, lets them create one organization.
- **W1** `platform/apps/web/`: Next.js App Router, React 19, TypeScript, Tailwind, Signal Room tokens from the design canvas; next-intl with all strings in `messages/en.json`; ESLint rules forbidding literal JSX text and physical left/right CSS; Vitest.
- **W2–W3** Screens per spec; frontend-design for the visual pass; accessible forms (labels, errors next to fields, focus management).
- **W4** Compose file in `platform/deploy/compose.yaml`; Playwright end-to-end for AC-9 and an RTL screenshot check for AC-9b; CI workflow `platform-core.yml`.
