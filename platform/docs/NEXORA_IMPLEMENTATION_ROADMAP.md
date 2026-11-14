# NEXORA AI: implementation roadmap

| | |
|---|---|
| Status | Draft for approval (document 6 of 6) |
| Features | `NEXORA_FEATURES.md` (standard vs unique) |
| Builds on | `NEXORA_SYSTEM_ARCHITECTURE.md`, `NEXORA_DATABASE_ARCHITECTURE.md`, `NEXORA_INTEGRATION_SPECIFICATION.md` |
| Sizing | S ≈ 1 day, M ≈ 2–4 days, L ≈ 1–2 weeks of focused work. No calendar dates: the plan defers dates until the first adapter contract tests pass |

## 0. Release goals

| Release | User-visible outcome |
|---|---|
| **R1: Portal foundation** | Sign up, create an organization and workspaces, invite members with roles, see a dashboard with system health |
| **R2: Voice Studio** | Create, edit, publish and test-call a voice agent (Dograh) from the NEXORA portal, see call history |
| **R3: AI Studio** | Create and run AI workflows (graphon in SaaS, Dify in a dedicated install), import Dify DSL |
| **R4: Cross-engine** | Link a voice agent to an AI workflow or knowledge base, and trace one call across both engines |
| **R5: Platform** | Knowledge Hub, Model Hub, MCP / Integration Hub, API keys + SDKs, usage dashboard |
| **R6: Enterprise** | SSO/SCIM, audit export, billing, approvals, retention, hardening, on-prem Helm |

Demo goal from the plan, reached at the end of R5: *a developer opens NEXORA, creates a
voice agent, connects it to an AI agent, attaches a knowledge base, connects MCP tools,
deploys it and monitors everything without knowing which engine runs what.*

## Parallel track: licence and legal (start now)
| # | Task | Output |
|---|---|---|
| L1 | Contact LangGenius (commercial-licence contact listed on dify.ai) describing NEXORA's architecture and asking for multi-tenant terms and whether several workspaces in one dedicated install count as multi-tenant | Written answer on file |
| L2 | Verify the `dify-sandbox` licence | Yes/no for reuse |
| L3 | Licence inventory for bundled plugins and Pipecat extras | `docs/legal/THIRD_PARTY.md` |
| L4 | Keep the Dograh BSD-2 notice and Apache NOTICE files (graphon, plugin daemon) in the About page and image | Compliance check in CI |

---

## Phase P0: repository and foundations
| # | Ticket | Size | Acceptance criteria |
|---|---|---|---|
| P0.1 | Set up the `platform/` monorepo in Voice-Analysis (layout from Architecture §12), pnpm + uv workspaces, pre-commit, CI (lint, type-check, tests) | M | `make dev` starts everything; CI green on an empty feature |
| P0.2 | Docker Compose dev stack: PostgreSQL 17 + pgvector, Redis, MinIO, pinned Dograh (`api`, `coturn`), plugin daemon, `nexora-core`, `nexora-ai-runtime`, `portal`. Dify behind a `dedicated` profile | M | One command boots the stack. Healthchecks pass. Dograh telemetry is off |
| P0.3 | `nexora-core` skeleton: FastAPI app, settings, async SQLAlchemy, Alembic, structured JSON logs, OTel, `/healthz` `/readyz` `/metrics` | M | Health endpoints work; a trace from a request appears in the local collector |
| P0.4 | Portal skeleton: Next.js 15, Tailwind, shadcn/ui, NEXORA design tokens (dark-first), app shell with the navigation from plan §11, generated API client | M | Shell renders with empty pages for every nav item; Lighthouse accessibility ≥ 90 |
| P0.5 | Secrets module (envelope encryption, local KEK in dev) | S | Secret round-trip test. Plaintext never logged |

## Phase P1: Core identity, tenancy, RBAC (→ R1)
| # | Ticket | Size | Acceptance criteria |
|---|---|---|---|
| P1.1 | DB migrations for DB §3.1–3.2 (orgs, workspaces, users, identities, sessions, memberships, invitations, roles, permissions) + seed + RLS policies | M | DB acceptance #1 (RLS isolation) passes |
| P1.2 | Email/password sign-up, verification, login, logout, password reset; server-side sessions | M | Session revoke logs the user out everywhere; brute-force throttling |
| P1.3 | OIDC login (Google, Microsoft) | M | Linking an existing email asks for confirmation, never auto-merges unverified emails |
| P1.4 | Organization + workspace CRUD; workspace provisioning job (creates engine accounts, P2.1 / P3.1) | M | Workspace shows `provisioning` → `active` or `failed` with reason |
| P1.5 | Members and invitations with the seven roles; permission checks as a FastAPI dependency | M | Table-driven test: every role × every permission × org/workspace scope |
| P1.6 | Audit log module (hash chain) wired into P1.2–P1.5 | S | DB acceptance #6 |
| P1.7 | Portal: sign-in/up, org switcher, workspace switcher, Members & Roles, Workspaces, profile | L | A new user can create an org, a workspace, invite a teammate, change a role |
| P1.8 | Dashboard v1: resource counts from the registry, System Health from `/readyz` aggregation | M | Health panel turns red within 30 s of stopping Dograh |

## Phase P2: Voice engine integration (→ R2)
| # | Ticket | Size | Acceptance criteria |
|---|---|---|---|
| P2.1 | `DograhVoiceEngine.provision_account`: resolve the **VERIFY** item (org creation path). One Dograh org per workspace, key stored in secrets | M | New workspace gets a Dograh org; key never returned by any API |
| P2.2 | Registry tables (DB §3.4) + outbox + reconciler skeleton | M | Integration acceptance #5 |
| P2.3 | Voice agent CRUD, publish, versions through the adapter; adapter contract tests in CI against pinned Dograh | L | Integration acceptance #1 for Dograh |
| P2.4 | Portal Voice Studio: agent list, create wizard (prompt, voice, STT/TTS/LLM choice, language), settings, versions | L | Agent created in the portal appears and runs in Dograh |
| P2.5 | Voice Flow Builder v1. **Interim option:** embed Dograh's builder (BSD-2 allows rebranding) behind NEXORA auth while the NEXORA React Flow builder is built (P2.6) | M | Users can edit conversation nodes without leaving NEXORA |
| P2.6 | NEXORA Voice Flow Builder on React Flow using Dograh `node_specs` | L | Round-trip: edit in NEXORA → publish → definition in Dograh matches |
| P2.7 | Test call in browser (WebRTC through gateway, short-lived token) and outbound test call | M | Test call works from the portal on Chrome and Safari |
| P2.8 | Engine events ingestion for Dograh (Integration §6.1), call history + transcript view | M | Integration acceptance #4 |
| P2.9 | Phone numbers and telephony provider setup screens (Twilio first) | M | Inbound call to a bought number reaches the agent |
| P2.10 | nexora-audio as a Dograh noise-reduction engine in the fork (`noise_reduction/factory.py`), selectable per agent | M | A/B toggle in agent settings; fail-open when the engine errors |

## Phase P3: AI engine integration (→ R3)
| # | Ticket | Size | Acceptance criteria |
|---|---|---|---|
| P3.1 | `nexora-ai-runtime` service: graphon 0.8.0 `GraphEngine` in workers, run limits, run API (Integration §3.2) | L | Sample workflow (start → llm → end) runs blocking and streaming |
| P3.2 | Plugin daemon wiring for model/tool plugins; credentials injected from Model Hub per run | M | Same workflow runs with OpenAI and Anthropic credentials of two different workspaces, no cross-leak |
| P3.3 | `GraphonEngine` adapter + contract tests | M | Integration acceptance #1 for graphon |
| P3.4 | Dify DSL import with node mapping report | M | Importing a Dify workflow with unsupported nodes lists them; supported ones run |
| P3.5 | NEXORA nodes: `nexora_knowledge_retrieval`, `nexora_agent` (tool-calling loop), `nexora_approval` | L | Each node unit-tested; agent node respects tool grants |
| P3.6 | `DifyAppEngine` adapter for dedicated installs (Service API) + guard | M | Integration acceptance #6; contract tests against pinned Dify 1.19.0 in the `dedicated` profile |
| P3.7 | Portal AI Studio: workflow list, runs, run detail with node timeline | L | A run's node inputs/outputs are visible and redacted for secrets |
| P3.8 | NEXORA AI Workflow Builder (React Flow, graphon node schema), own design, no Dify UI reuse | L | Build, save, run a branching workflow entirely in the portal |
| P3.9 | Chat apps / AI agents (agent = workflow with `nexora_agent` node + preview chat) | M | Preview chat streams tokens in the portal |

## Phase P4: Cross-engine orchestration (→ R4)
| # | Ticket | Size | Acceptance criteria |
|---|---|---|---|
| P4.1 | Tool bindings + signed internal tool-call endpoint (Integration §4) | M | Bad signature or replay older than 5 minutes is rejected |
| P4.2 | `upsert_tool` on Dograh: creates the custom HTTP tool on the agent (resolve header-templating **VERIFY**) | M | Linking in the portal creates the tool in Dograh |
| P4.3 | Sync / sync_then_async / async modes, deadlines, circuit breaker, `get_result` companion tool | M | Integration acceptance #3 |
| P4.4 | Workspace MCP server exposing bindings as MCP tools (alternative to P4.2) | M | Dograh MCP tool lists and calls the workspace's targets |
| P4.5 | Portal "Connections" tab on a voice agent: pick workflow / knowledge base, map inputs, set the `say` template, test | M | Insurance demo from the plan works end to end |
| P4.6 | Unified execution trace view (executions + steps + OTel spans) | M | Integration acceptance #2 |

## Phase P5: Platform modules (→ R5)
| # | Ticket | Size | Acceptance criteria |
|---|---|---|---|
| P5.1 | Knowledge Hub base: knowledge bases, upload, pgvector back end, Knowledge API, permissions (detail in Phase PK) | M | Upload → `ready` → retrieve returns cited chunks; Integration §11.10 #1 |
| P5.3 | Model Hub: providers, verification, named configs, propagation to engines with status | M | Changing a key updates Dograh and the AI runtime; status per engine shown |
| P5.4 | Integration Hub: MCP server registration, tool discovery, tool grants per agent | M | An agent without a grant cannot call a discovered tool (test) |
| P5.5 | API keys, OAuth client credentials, rate limits, idempotency | M | DB acceptance #5; 429 with `Retry-After` |
| P5.6 | Outgoing webhooks (signed, retried) | S | Delivery log in portal with replay |
| P5.7 | Usage pipeline: events from engines + gateway, hourly roll-up, usage page and dashboard tiles | M | Voice minutes in NEXORA match Dograh run durations within 1 % |
| P5.8 | Public OpenAPI, developer portal (`apps/docs`), Python + TypeScript SDKs generated and hand-polished | L | Quickstart: create voice agent → link workflow → place test call in under 15 lines of SDK code |

## Phase PK: Knowledge and RAG (→ R5, spec: Integration §11)
| # | Ticket | Size | Acceptance criteria |
|---|---|---|---|
| K1 | Parser benchmark on real customer documents (Arabic PDFs, scans, table-heavy policies, XLSX, email): Docling vs Unstructured OSS vs Arabic OCR candidates | M | Scores per file type for text accuracy, table structure, reading order; defaults chosen from results and recorded |
| K2 | `DocumentParser` interface + Docling adapter + Unstructured adapter + per-page quality check and fallback | L | Failing page re-parsed by the second parser; best result kept and logged |
| K3 | NEXORA chunker: structure-aware, parent–child, context prefix, metadata, tokenizer-based sizes | M | Same document parsed by either parser yields chunks with identical section paths |
| K4 | Tables: small vs large tables, row sentences, JSON copy | M | Integration §11.10 #2 (row and column counts match) |
| K5 | Figures: storage, OCR text, vision description, chart values | M | Figures searchable by their content; voice mode returns description only |
| K6 | Structured knowledge: XLSX/CSV to sandboxed DuckDB, read-only `query_table` tool | L | Integration §11.10 #3 |
| K7 | Arabic: normalisation, Arabic OCR engine from K1, mixed Arabic/English | M | Integration §11.10 #6 |
| K8 | Retrieval: query rewrite, filters first, hybrid search + RRF, reranking, minimum score, citations | L | Hit rate at 5 ≥ target on the K1 test set; `no_answer` instead of low-score answers |
| K9 | Voice mode: deadline, cache, prefetch, short answers | M | Integration §11.10 #4 |
| K10 | Website crawler (sitemap, main content, re-crawl schedule) and email, EPUB, RTF, ODT, audio/video files | M | Each format ingests with citations back to source position |
| K11 | Knowledge Hub UI: chunk preview, per-page re-run, search test screen | L | A user sees how a document was split and why a passage matched |
| K12 | Retrieval tests, test runs on reindex / model change / parser upgrade, feedback from wrong answers | M | Integration §11.10 #5 |
| K13 | `DifyDatasetKnowledge` back end for dedicated installs (was P5.2) | M | Same Knowledge API passes the same tests on both back ends |

## Phase PU: NEXORA differentiators (spec: `NEXORA_FEATURES.md` §1)
| # | Ticket | Size | Acceptance criteria |
|---|---|---|---|
| U2.1 | Audio quality metrics from nexora-audio per call (noise, echo, background talkers, packet loss, clipping, turn timing) into usage/executions | M | Every call has a quality record; dashboard tile and agent call list show it |
| U2.2 | "Misheard or misunderstood" view in the trace: audio score, STT confidence, retrieval and model steps side by side | M | A test call with injected noise is classified as an audio problem, a wrong answer with clean audio as a model problem |
| U4.1 | Answer-budget visual in trace and live lanes (budget line, holding line marker) | S | Builds on P4.3; holding line visible in trace and dashboard |
| U6.1 | Mid-call approvals: approval inbox, push notification, approve or reject while the call waits on a holding line | M | Payment-style tool waits; approve continues the call; reject is spoken gracefully; audit written |
| U6.2 | Masking of personal data in transcripts, traces and exports by role | M | Viewer sees masked phone numbers and IDs; Operator and above see them; export respects role |
| U5.1 | Supervisor listen, whisper, take over, hand back | L | Supervisor joins a live call; AI resumes with full context after hand-back |
| U3.1 | Channels: web chat widget and WhatsApp for the same agent; one publish to all channels | L | Same knowledge and tools answer on phone and chat; version shown per channel |
| U1.1 | Failure clustering: group failed and transferred calls by cause using transcripts, traces and audio score | M | Clusters with counts and example calls on an Insights page |
| U1.2 | Proposed fix: model drafts a flow or prompt change per cluster as a reviewable diff | M | Fix opens as a draft version, never published automatically |
| U1.3 | Real calls to test set: selected calls replayed as simulations against the draft (synthetic caller with the original wording) | L | Draft must pass the cluster's test set before rollout |
| U1.4 | Traffic split rollout and result report (default 10 % for 24 h) | M | Promotion only on a measured improvement; one-click rollback |
| U7.1 | Bring your own agent: register an external agent WebSocket as a NEXORA resource with audio, monitoring and governance | M | External agent calls appear in executions, analytics and audit like native ones |
| U8.1 | Cost per call and per outcome; latency- and cost-aware model routing within the answer budget | M | Cost per resolved call report; router never exceeds the configured latency budget in tests |
| U9.1 | Arabic STT/TTS provider benchmark and adapters, dialect routing, Arabic/English mixing | L | Chosen providers beat the baseline on Saudi call audio; routing picks a provider per detected dialect |
| U9.2 | Portal right-to-left layout and Hijri dates | M | All screens pass an RTL review; dates switch per user setting |

## Phase P6: Enterprise readiness (→ R6)
| # | Ticket | Size | Acceptance criteria |
|---|---|---|---|
| P6.1 | SAML SSO + SCIM provisioning | L | Okta and Entra ID test tenants |
| P6.2 | Approvals for sensitive tools (portal inbox, email notification, expiry) | M | Payment-style tool waits for approval; rejection is spoken gracefully |
| P6.3 | Billing: plans, quotas, Stripe metered subscriptions | L | Quota exceeded → clear error, no engine call made |
| P6.4 | Retention jobs, data export, org deletion (including engine data via adapters) | M | Deleted org leaves no rows in NEXORA and no objects in its engine accounts |
| P6.5 | Dedicated-install automation: Helm/Terraform for a customer environment with Dify (single workspace) | L | New dedicated customer environment from one pipeline run |
| P6.6 | On-prem Helm chart (NEXORA + Dograh base chart), telemetry off by default | L | Air-gapped install guide verified |
| P6.7 | Load tests (concurrent calls with cross-engine tool calls), soak, chaos (engine down) | M | Defined SLOs met. Engine outage degrades only the affected features |
| P6.8 | Security review: threat model, dependency scanning, pen test, secrets rotation drill | M | No open critical/high findings |

## Definition of done (every ticket)
- Tests: unit + integration. Adapters have contract tests against the pinned engine version.
- Permissions enforced and covered by a negative test.
- Audit event written for every state change by a user.
- No secret, prompt content or audio in logs at info level.
- API changes reflected in OpenAPI and the generated client.
- Portal screens: loading, empty and error states; keyboard accessible.

## Suggested order of work
P0 → P1 → P2.1–P2.4 → P3.1–P3.3 → P4.1–P4.3 (first cross-engine demo) → rest of P2/P3 →
P4.4–P4.6 → P5 with PK (K1 parser benchmark can start any time) → PU, starting with U2.1, U4.1, U6.1 and U1.1 (the launch story) → P6. This front-loads the riskiest unknowns: the Dograh provisioning path,
graphon maturity and the voice-to-AI latency budget.

## Top risks
| Risk | Mitigation |
|---|---|
| Dograh has no service-level org-provisioning API | Superuser service account, else a minimal patch in the fork (P2.1) |
| graphon 0.x API changes | Pin version; adapter isolates it; contract tests on upgrade |
| Voice latency with cross-engine calls | Deadlines below Dograh's 5 s tool timeout; `sync_then_async`; pre-warm runtime workers |
| Licence change by LangGenius | SaaS never depends on the Dify app; Dify used only per-customer and version-pinned |
| Scope size (two large engines) | Ship R1 → R4 first; treat R5/R6 items as separately prioritised |
