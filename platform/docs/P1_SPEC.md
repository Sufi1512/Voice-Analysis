# P1 NEXORA Core: specification

Status: **draft, waiting for approval** (no implementation before approval)   ·   Date: 2026-11-14

Builds on: `NEXORA_SYSTEM_ARCHITECTURE.md` §3, §7; `NEXORA_DATABASE_ARCHITECTURE.md` §3.1–3.4,
§3.9; `NEXORA_IMPLEMENTATION_ROADMAP.md` P0 (repo foundations) and P1. P0 (pinned Dograh with
nexora-audio, CI) is done on branch `platform/p0-foundations`.

Process for this phase: grilling on the open questions below → this spec updated and approved →
tickets → tdd → code review; the portal parts also use frontend-design.

## Problem and goal
NEXORA needs its own control plane before any engine work: who a user is, which organization and
workspace they act in, and what they may do. Success: a new user signs up, creates an organization
and a workspace, invites a teammate with a role, and every API call is authorized and isolated by
organization, proven by tests, in CI on Linux.

## Scope
### In scope
- `platform/services/core/`: FastAPI service, Python 3.13, async SQLAlchemy 2 + asyncpg, Alembic,
  PostgreSQL 17, Redis. Health (`/healthz`, `/readyz`), metrics, JSON logs, OpenTelemetry.
- Identity: email + password (argon2id), email verification, password reset, server-side sessions
  (HttpOnly cookie), logout everywhere; Google and Microsoft sign-in (OIDC).
- Tenancy: organizations, workspaces (development / staging / production), memberships, invitations.
- Authorization: the seven roles and permission catalogue (DB doc §3.2), checked per request;
  PostgreSQL row-level security on every tenant table.
- Resource registry tables (DB doc §3.4) and engine tables (§3.3), without engine calls yet.
- Audit log, append-only with hash chain (DB doc §3.9).
- Secrets module (envelope encryption, local key in development).
- Portal shell (`platform/apps/web`): Next.js, Signal Room tokens, sign-in / sign-up, organization
  and workspace switchers, Members and roles, Workspaces, an Overview page with system health.
- Local stack: Docker Compose for Core, PostgreSQL, Redis, portal (Dograh optional profile).
- CI: Core tests (with PostgreSQL service), portal unit and Playwright tests, Linux only.

### Out of scope
- Engine provisioning and voice agents (P2), AI workflows (P3), SAML / SCIM (P6), billing.
- Any change to Dograh beyond P0's patch; any push to `Sufi1512/dograh` or `Sufi1512/dify`.

## Behaviour (main flows)
1. Sign up → verification email → first login creates no organization; the user is asked to create one.
2. Create organization → the creator is Organization owner → a default "Production" workspace is created.
3. Invite by email with a role and scope (organization or one workspace) → invite link valid 7 days →
   accepting creates the membership.
4. Every API request resolves session or API key → user → active organization → permission check →
   the database transaction sets `nexora.org_id` for row-level security.
5. Role change or removal takes effect on the next request; removing the last Organization owner is refused.

Errors: wrong password (generic message, rate-limited per IP and per email), expired invite, duplicate
membership, permission denied (403 with the missing permission named), unknown organization (404, never 403, so existence does not leak).

## Interfaces (proposed NEXORA API, `/v1`)
`POST /auth/signup`, `/auth/login`, `/auth/logout`, `/auth/password-reset`, `GET /auth/oidc/{provider}`,
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
- [ ] AC-3 Sign-up, verification, login, logout, logout everywhere and password reset work end to end; 10 failed logins in a minute lock further attempts for that email for 15 minutes.
- [ ] AC-4 Google and Microsoft sign-in link to an existing verified account only after confirmation.
- [ ] AC-5 Invitations: accept within 7 days creates the membership; expired or reused links are refused.
- [ ] AC-6 The last Organization owner cannot be removed or demoted.
- [ ] AC-7 Every state change writes an audit row; the hash chain verifies; update and delete are refused.
- [ ] AC-8 Migrations run up and down cleanly on an empty database.
- [ ] AC-9 Portal: a new user can sign up, create an organization, see the Production workspace, invite a teammate and change their role (Playwright).
- [ ] AC-10 CI runs all of the above on Linux on every change under `platform/services/core/**` or `platform/apps/web/**`.

## Open questions (for grilling before approval)
1. **SaaS or enterprise first?** Changes whether self-service sign-up is on by default or invite-only.
2. **Data region** for the first deployment (for example in-Kingdom): affects hosting and the email provider.
3. **Email provider** for verification and invites (needs an account; none chosen yet).
4. **Default role for invited users** (proposed: Developer for workspace invites, Viewer for organization invites).
5. **Portal languages at launch**: English only, or English and Arabic (right-to-left) from P1.
6. **Team size**: affects how much of P1 runs in parallel.
