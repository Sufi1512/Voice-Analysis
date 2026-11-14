# NEXORA AI platform

NEXORA unifies Dograh (voice engine) and an AI engine (Dify app for single-tenant
installs, graphon for shared SaaS) behind one branded portal, API and control plane.

## Source of truth
Read before changing anything:
- `docs/NEXORA_SYSTEM_ARCHITECTURE.md`
- `docs/NEXORA_DATABASE_ARCHITECTURE.md`
- `docs/NEXORA_INTEGRATION_SPECIFICATION.md`
- `docs/NEXORA_IMPLEMENTATION_ROADMAP.md` (tickets P0.1 onward)
- `docs/NEXORA_PRODUCT_PLAN.md` ("NEXORA AI – Platform Analysis & Plan")
- Phase specs: `docs/P0_SPEC.md` (approved, built), `docs/P0_IMPLEMENTATION_DECISIONS.md`, `docs/P0_TICKETS.md`; drafts awaiting approval: `docs/P1_SPEC.md`, `docs/WORKFLOW_RUNNER_SPEC.md`
- `docs/NEXORA_FEATURES.md` (feature catalogue, standard vs unique)
- Design: Signal Room canvas https://claude.ai/artifact/9w5bzWzzctRNkfz7b7ESzD

Engine audits: `docs/DOGRAH_DEEP_TECHNICAL_AUDIT.md`, `docs/DIFY_DEEP_TECHNICAL_AUDIT.md`. Paths in this file are relative to `platform/`.

## Rules
0. Per phase: grilling → to-spec → to-tickets → tdd → code-review (frontend-design for the web app). No implementation before the user approves that phase's spec. Never push to `Sufi1512/dograh` or `Sufi1512/dify`: Dograh changes are patch files in `engines/dograh/patches/`. Linux only.
1. Work ticket by ticket from the roadmap. A ticket is done only when its acceptance
   criteria and the roadmap's definition of done are met.
2. Never invent an engine endpoint. Anything marked **VERIFY** must be confirmed against
   the pinned engine version and recorded in tests.
3. The shared SaaS must never depend on the Dify application (licence). Dify code runs
   only in dedicated, single-tenant installs.
4. Never commit secrets, engine API keys, recordings or customer data.
5. Every tenant-owned table has `organization_id` and row-level security.
6. Keep vendored skills in `/.claude/skills/` (repo root) unchanged except as listed in `/.claude/SKILLS.md`.

## Skills to use
- Planning a phase or feature: `brainstorming`, `writing-plans`, `planning-with-files`.
- Building: `test-driven-development`, `executing-plans`, `systematic-debugging`,
  `verification-before-completion`.
- Portal UI: `ui-ux-pro-max` and frontend-design (account skill), then
  `vercel-react-best-practices`, `vercel-composition-patterns`; audit screens with
  `vercel-web-design-guidelines`.
- Before merging: `requesting-code-review`; security-sensitive changes (auth, RBAC,
  tenancy, secrets, engine adapters) also `tob-differential-review` and `tob-sharp-edges`.
- Python backend: `tob-modern-python`, `tob-property-based-testing`.
- Dependencies: `tob-supply-chain-risk-auditor`. Static checks: `tob-semgrep`.
