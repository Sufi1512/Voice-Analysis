# Krisp.ai — Investigation Master Plan

Goal: an evidence-backed blueprint of Krisp's observable product behaviour and
documented integration contracts, mapped to an independent implementation.
Out of scope: private source code, proprietary models, licensed SDK internals.

Status legend: NOT_STARTED · IN_PROGRESS · REVIEW · COMPLETE
Confidence legend: see `CLAUDE.md`.

## Module overview

| # | Module | Priority | Folder | Depends on | Status |
|---|---|---|---|---|---|
| 1 | Public website | P2 (run first — feeds inventory) | 00-product-discovery | — | IN_PROGRESS |
| 2 | AI Meeting Assistant | P1 | 01-meeting-assistant | 1, 9 | NOT_STARTED |
| 3 | Call Center AI | P1 | 02-call-center | 1, 5 | NOT_STARTED |
| 4 | Developer Platform | P0 | 03-developer-platform | 1 | IN_PROGRESS |
| 5 | Real-time Audio Engine | P0 | 04-audio-engine | 4 | NOT_STARTED |
| 6 | Admin & Workspace | P1 | 05-admin | 1 | NOT_STARTED |
| 7 | Billing & Licensing | P2 | 06-billing | 1, 6 | NOT_STARTED |
| 8 | Integrations | P2 | 07-integrations | 2, 3, 4 | NOT_STARTED |
| 9 | Security & Privacy | P1 | 08-security-privacy | all | NOT_STARTED |

Suggested order: 1 → 4 → 5 → 2 → 3 → 6 → 7 → 8 → 9 → synthesis
(`08_MASTER_ARCHITECTURE.md`).

---

## 1. Public website
**Questions**
- What product families, features and plans are advertised?
- What is the navigation structure, and where does each CTA lead (signup, demo, docs, download)?
- Which features are gated by plan (Free / Pro / Business / Enterprise)?
- What onboarding entry points exist (web signup, desktop download, sales form)?

**Browser evidence:** full-page screenshots of homepage, AI Meeting Assistant,
Call Center AI, Developers, Pricing; nav/dropdown captures; CTA destination
list; responsive captures at mobile/tablet/desktop.
**Documentation:** `00-product-discovery/PAGE_INVENTORY.md` (Page ID, URL,
section, component, interaction, expected behaviour, evidence, confidence),
`01_PRODUCT_DISCOVERY.md`.
**Unknowns:** features only in sales collateral; region-specific pricing.
**Done when:** every top-level page and nav item inventoried with evidence;
pricing/plan matrix captured; product inventory draft exists.

## 2. AI Meeting Assistant
**Questions**
- How is a meeting captured (desktop app virtual mic/speaker, bot, calendar join)?
- Recording modes, transcription languages, speaker attribution behaviour?
- How are notes, summaries, action items generated and edited?
- How does meeting AI chat scope its answers (single meeting vs all)?
- Sharing, search, retention, export options?
- Noise cancellation / accent conversion controls in this product?

**Browser evidence:** authorized account walkthrough of dashboard, a meeting
you recorded yourself (test data only), transcript, notes, chat, settings,
integrations; all 10 UI states per screen; sanitized network notes.
**Documentation:** `05_MEETING_ASSISTANT.md`, meeting lifecycle state diagram,
proposed meeting data model.
**Dependencies:** a legitimate Krisp account; desktop app installed.
**Unknowns:** server-side processing location/timing; summarisation models.
**Done when:** full lifecycle (scheduled → recording → processing → ready →
shared/deleted) mapped with evidence; failures documented.

## 3. Call Center AI
**Questions**
- Which capabilities exist (Agent Assist, Knowledge Chat, Speech Analytics, QA
  scorecards, compliance, Voice Security, Accent Conversion, Voice Translation,
  summaries)?
- What are agent, supervisor and admin roles able to see/do?
- How does it attach to telephony/CCaaS platforms?

**Evidence:** public product pages, help center, published demos/videos;
authorized access only if available (most likely NOT_ACCESSIBLE).
**Documentation:** `06_CALL_CENTER_ARCHITECTURE.md` with capability →
input events → processing → output → permissions → data lifecycle.
**Unknowns:** most internals; expect heavy HYPOTHESIS labelling.
**Done when:** every advertised capability has a row with source and
confidence; inaccessible items clearly marked.

## 4. Developer Platform
**Questions**
- What SDKs/APIs exist (VIVA SDK, RTC SDK, Browser SDK, Cloud API)?
- Which capabilities does each offer (voice isolation, noise cancellation,
  background voice cancellation, VAD, turn-taking, interrupt prediction,
  translation)?
- Supported platforms, languages, sample rates, frame sizes, licensing model?
- Cloud API transport (WebSocket?) and message contracts as documented?

**Evidence:** official docs at developers-docs.krisp.ai and sdk-docs.krisp.ai
(save URL + capture date + key excerpts paraphrased in `reference/public-documentation/`).
**Documentation:** capability matrix (VIVA / RTC / Browser / Cloud API) with
every cell sourced; `03_API_BACKEND_ARCHITECTURE.md` (documented contracts).
**Done when:** capability matrix has zero unsourced cells; licensing/pricing
model for SDKs captured or marked UNKNOWN.

### Claims from the playbook to verify first
| Claim | Status |
|---|---|
| VIVA & RTC SDKs process on customer side; API processes in cloud over WebSocket | PARTLY VERIFIED (E022, E032) |
| VIVA pipeline order: voice isolation → VAD → turn detection → STT | VERIFIED for isolation → turn/STT (E025) |
| Voice Isolation latency ≈ 20 ms | NOT FOUND (E036) |
| Interrupt prediction distinguishes backchannels from real interruptions | VERIFIED (E023) |
| Browser SDK uses Web Audio / Workers / WASM | WASM VERIFIED (E031); rest UNKNOWN |

See `investigation/03-developer-platform/DEVELOPER_PLATFORM.md`.

## 5. Real-time Audio Engine
**Questions**
- Observable latency, CPU usage and quality of noise cancellation in the
  desktop app under the test matrix below.
- Documented frame durations, sample rates, model variants (from module 4).
- Where in the chain do echo cancellation, VAD and isolation sit?

**Evidence:** controlled recordings you create (no third-party voices without
consent), stored in `reference/recordings/` with a metadata sheet.

| Scenario | Test | Behaviour to observe |
|---|---|---|
| Clean voice | Single speaker | Speech preserved |
| Keyboard | Speech + typing | Keyboard noise reduced |
| Traffic | Speech + traffic | Background reduced |
| Cross-talk | Two speakers | Primary voice isolated |
| Silence | No speech | Inactivity detected |
| Backchannel | "uh-huh / yeah" | No false interruption |
| Barge-in | Speak over AI | Genuine interruption detected |
| Echo | Speaker playback | Echo reduced |
| Network jitter | Variable timing | Continuity maintained |
| Languages | English / Arabic | Language handling |

**Documentation:** `04_AUDIO_AI_ARCHITECTURE.md` — pipeline diagram,
interface contracts, latency budget proposal, test matrix with our own
acceptance thresholds.
**Done when:** each scenario run and logged; no claims about Krisp's internal
models beyond what docs state.

## 6. Admin & Workspace
**Questions:** users, teams, roles, invitations, permissions, org settings,
policies, SSO/SCIM, audit events.
**Evidence:** authorized admin console (if available), help-center articles.
**Documentation:** `07_ENTERPRISE_ADMIN.md` — RBAC matrix, workspace entity
model, admin workflows, permission test matrix, proposed multi-tenant schema.
**Done when:** every observed role/permission sourced; inaccessible enterprise
features marked NOT_ACCESSIBLE.

## 7. Billing & Licensing
**Questions:** plans, limits (minutes, meetings, seats), trial behaviour,
upgrade/downgrade flows, SDK licensing.
**Evidence:** pricing page, account billing screen (no card data captured).
**Documentation:** plan/limit matrix, subscription state diagram.
**Done when:** each plan limit sourced; payment-provider integration noted
only if visibly observable.

## 8. Integrations
**Questions:** calendars, conferencing apps (Zoom, Meet, Teams, Slack),
CRM/notes destinations, CCaaS/telephony, webhooks/API keys.
**Evidence:** integrations pages, help center, authorized connect/disconnect
flows (OAuth scope screens captured, tokens never).
**Documentation:** `INTEGRATIONS.md` — per integration: direction, data,
auth method, trigger, failure behaviour.
**Done when:** every listed integration has a row with source.

## 9. Security & Privacy
**Questions:** published certifications (SOC 2, ISO, HIPAA, GDPR), data
residency, retention, on-device vs cloud processing per feature, encryption
claims, recording consent/notification behaviour.
**Evidence:** trust/security pages, privacy policy, DPA, observed consent UI.
**Documentation:** `SECURITY_OBSERVATIONS.md`; threat model for our own design
in `architecture/security/`.
**Done when:** each claim sourced; our design's controls listed with tests.

---

## Final deliverables
`PRODUCT_OVERVIEW.md`, `FEATURE_INVENTORY.md`, `USER_JOURNEYS.md`,
`FRONTEND_ARCHITECTURE.md`, `API_DOCUMENTATION.md`, `DATA_MODEL.md`,
`AUDIO_PIPELINE.md`, `AI_ARCHITECTURE.md`, `MEETING_ASSISTANT.md`,
`CALL_CENTER_ARCHITECTURE.md`, `ENTERPRISE_ADMIN.md`, `INTEGRATIONS.md`,
`SECURITY_OBSERVATIONS.md`, `TEST_CASES.md`, `IMPLEMENTATION_ROADMAP.md`,
`INVESTIGATION_GAP_ANALYSIS.md`.

## Completion checklist
- [ ] All three product families investigated
- [ ] Public website and onboarding mapped
- [ ] Authorized application workflows documented
- [ ] All accessible UI states captured
- [ ] Sanitized API observations completed
- [ ] WebSocket events documented where accessible
- [ ] Audio architecture and capability matrix completed
- [ ] Meeting Assistant lifecycle mapped
- [ ] Call Center workflows mapped
- [ ] Admin and RBAC mapped
- [ ] Database and event models proposed
- [ ] Security and privacy analysis completed
- [ ] Evidence ledger reviewed
- [ ] Unknowns and assumptions documented
- [ ] Implementation roadmap approved
