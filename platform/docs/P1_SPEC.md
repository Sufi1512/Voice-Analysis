# P1 NEXORA Core: specification

Status: **draft, waiting for approval** (no implementation before approval)   ·   Date: 2026-11-14   ·   Grilling done 2026-11-14 (decisions below)

Builds on: `NEXORA_SYSTEM_ARCHITECTURE.md` §3, §7; `NEXORA_DATABASE_ARCHITECTURE.md` §3.1–3.4,
§3.9; `NEXORA_IMPLEMENTATION_ROADMAP.md` P0 (repo foundations) and P1. P0 (pinned Dograh with
nexora-audio, CI) is done on branch `platform/p0-foundations`.

Process for this phase: grilling on the open questions below → this spec updated and approved →
tickets → tdd → code review; the portal parts also use frontend-design.

## Problem and goal
NEXORA needs its own control plane before any engine work: who a user is, which organization and
workspace they act in, and what they may do. **Enterprise first:** the platform owner creates
organizations and invites their admins; there is no public sign-up in P1. Success: the platform
owner creates an organization and invites its owner; that owner signs in (with MFA), sees the
Production workspace, invites a teammate, and every API call is authorized and isolated by
organization, proven by tests, in CI on Linux.

## Scope
### In scope
- `platform/services/core/`: FastAPI service, Python 3.13, async SQLAlchemy 2 + asyncpg, Alembic,
  PostgreSQL 17, Redis. Health (`/healthz`, `/readyz`), metrics, JSON logs, OpenTelemetry.
- Identity: email + password (argon2id), email verification, password reset, server-side sessions
  (HttpOnly cookie), logout everywhere; **TOTP MFA** (authenticator app, with recovery codes),
  required for Platform owner, Organization owner and Organization admin, optional for others;
  **Microsoft sign-in** (OIDC, Entra ID). Google sign-in is out of P1.
- Accounts are created only by invitation; self sign-up exists behind a setting
  `NEXORA_SELF_SIGNUP` that is off by default (enterprise first).
- Platform owner tools: create an organization and invite its first Organization owner; the first
  platform owner is created from environment variables on first start.
- Email through **SMTP** configured at deploy time (host, port, TLS, user, sender); Mailpit as the
  local mail catcher in Docker Compose and tests. No email-provider API.
- Tenancy: organizations, workspaces (development / staging / production), memberships, invitations.
- Authorization: the seven roles and permission catalogue (DB doc §3.2), checked per request;
  PostgreSQL row-level security on every tenant table.
- Resource registry tables (DB doc §3.4) and engine tables (§3.3), without engine calls yet.
- Audit log, append-only with hash chain (DB doc §3.9).
- Secrets module (envelope encryption, local key in development).
- Portal shell (`platform/apps/web`): Next.js, Signal Room tokens, sign-in, MFA setup and prompt,
  invitation acceptance, organization and workspace switchers, Members and roles, Workspaces,
  Platform admin (organizations), an Overview page with system health. **English only, built
  right-to-left ready**: every string through translation keys, CSS logical properties only
  (no left/right), so Arabic is a translation file and a `dir` switch later.
- Local stack: Docker Compose for Core, PostgreSQL, Redis, portal (Dograh optional profile).
- CI: Core tests (with PostgreSQL service), portal unit and Playwright tests, Linux only.

### Out of scope
- Engine provisioning and voice agents (P2), AI workflows (P3), SAML / SCIM (P6), billing.
- Google sign-in, public self sign-up (built but switched off), the Arabic translation itself.
- Hosting: P1 runs on Docker Compose; the in-Kingdom production deployment is its own ticket set later.
- Any change to Dograh beyond P0's patch; any push to `Sufi1512/dograh` or `Sufi1512/dify`.

## Behaviour (main flows)
1. Platform owner creates an organization and enters the first owner's email → invitation email →
   the invitee sets a password, verifies the email by accepting, and must set up MFA before entering.
   A default "Production" workspace is created with the organization.
2. Sign-in: email + password, then the TOTP code when MFA is on; or Microsoft sign-in, which links to
   an existing invited account only after the user confirms with their password or invite link.
3. Invite by email with a role and scope (organization or one workspace); **the role defaults to
   Viewer**; invite link valid 7 days, single use → accepting creates the membership.
4. Every API request resolves session or API key → user → active organization → permission check →
   the database transaction sets `nexora.org_id` for row-level security.
5. Role change or removal takes effect on the next request; removing the last Organization owner is refused.

Errors: wrong password (generic message, rate-limited per IP and per email), expired invite, duplicate
membership, permission denied (403 with the missing permission named), unknown organization (404, never 403, so existence does not leak).

## Interfaces (proposed NEXORA API, `/v1`)
`POST /auth/login`, `/auth/logout`, `/auth/logout-all`, `/auth/password-reset`, `/auth/mfa/setup`, `/auth/mfa/verify`,
`GET /auth/oidc/microsoft`, `POST /auth/signup` (404 unless `NEXORA_SELF_SIGNUP` is on),
`GET|POST /platform/organizations` (Platform owner only),
`GET /me`, `GET|POST /organizations`, `GET|PATCH /organizations/{org}`, `GET|POST /organizations/{org}/workspaces`,
`GET|POST /organizations/{org}/members`, `PATCH|DELETE /organizations/{org}/members/{id}`,
`POST /organizations/{org}/invitations`, `POST /invitations/{token}/accept`, `GET /organizations/{org}/audit-logs`.

## Non-functional requirements
- p95 under 150 ms for authenticated reads on the local stack.
- Session cookie: HttpOnly, Secure, SameSite=Lax; CSRF token on state-changing requests from the portal.
- No secrets, passwords or tokens in logs; audit rows cannot be updated or deleted by the app role.
- Portal: keyboard accessible, WCAG 2.2 AA contrast in both themes, reduced motion respected.

## Acceptance criteria
- [ ] AC-1 A user of organization A cannot read or change any row of organization B, through the API or a direct query as the app role (RLS test).
- [ ] AC-2 Every endpoint × role combination returns the expected allow or deny (table-driven test generated from the permission catalogue).
- [ ] AC-3 Invitation acceptance, login, logout, logout everywhere and password reset work end to end, with email delivered through SMTP (Mailpit in tests); 10 failed logins in a minute lock further attempts for that email for 15 minutes.
- [ ] AC-4 Microsoft sign-in links to an existing invited account only after confirmation, and never creates an account on its own.
- [ ] AC-4b TOTP MFA: owners and admins cannot reach any page or API except MFA setup until it is set up; a wrong code is refused; each recovery code works once.
- [ ] AC-4c With `NEXORA_SELF_SIGNUP` off (default), the sign-up endpoint returns 404 and the portal shows no sign-up link.
- [ ] AC-4d An invite created without choosing a role grants Viewer.
- [ ] AC-5 Invitations: accept within 7 days creates the membership; expired or reused links are refused.
- [ ] AC-6 The last Organization owner cannot be removed or demoted.
- [ ] AC-7 Every state change writes an audit row; the hash chain verifies; update and delete are refused.
- [ ] AC-8 Migrations run up and down cleanly on an empty database.
- [ ] AC-9 Portal: the platform owner creates an organization; the invited owner accepts, sets up MFA, sees the Production workspace, invites a teammate and changes their role (Playwright).
- [ ] AC-9b Portal is right-to-left ready: no hard-coded user-facing strings outside translation files, and no physical left/right CSS (lint rules in CI); switching `dir="rtl"` renders every P1 screen without overlap (Playwright screenshot check).
- [ ] AC-10 CI runs all of the above on Linux on every change under `platform/services/core/**` or `platform/apps/web/**`.

## Decisions (grilling, 2026-11-14)
| Decision | Reason |
|---|---|
| Enterprise first: invite-only, self sign-up built but off | User's choice; enterprise customers are onboarded by the platform owner |
| Data stays in Saudi Arabia | User's choice; rules out providers that process customer data abroad |
| Email via plain SMTP set at deploy time; Mailpit locally | Works with an in-Kingdom mail server or the customer's own |
| Invited users default to Viewer | Least access by default |
| English now, right-to-left ready (translation keys, logical CSS) | Arabic later without retrofitting every screen |
| Email + password with TOTP MFA (required for owners and admins) plus Microsoft sign-in; no Google | Most Saudi enterprises use Microsoft 365; SAML stays in P6 |

## Open questions
- None blocking P1. Team size was not asked; tickets stay sequential either way.
