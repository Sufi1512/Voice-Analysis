# Dograh: deep technical audit (for NEXORA AI)

| | |
|---|---|
| Source audited | Fork `Sufi1512/dograh`, commit `d672de2947da691fbc4542b62b914547a80e01ab` (2026-11-13, synced with `dograh-hq/dograh` main) |
| Pipecat | Git submodule `pipecat` → `dograh-hq/pipecat` (a Dograh fork of Pipecat), pinned at `9ac08e90be4bb83e506f3d10deaa8e6d31588547`. Not checked out in this audit |
| Licence | **BSD 2-Clause**, © 2025 Zansat Technologies Private Limited (`LICENSE`). Commercial use, modification, rebranding and SaaS allowed; keep the copyright notice |
| Method | Read of the source tree, models, routes, services, compose and Docker files. Findings cite file paths |

## 1. What Dograh is
A self-hostable voice-agent platform: visual workflow builder for conversations, telephony
(inbound/outbound), WebRTC, campaigns, knowledge base, tools/MCP, recordings, usage and
quotas. Real-time audio runs on Pipecat.

## 2. Size and stack

| Area | Facts |
|---|---|
| Backend | `api/`: FastAPI, async SQLAlchemy 2 + asyncpg, Alembic (109 migrations), ARQ + Redis, MinIO/S3, Python **3.13 only** (`requires-python >=3.13,<3.14`). ~131k lines of Python, 361 test files |
| Frontend | `ui/`: Next.js 15, React 19, TypeScript, Tailwind. ~87k lines |
| Voice runtime | Pipecat fork, installed in the image with extras `cartesia, deepgram, openai, elevenlabs, groq, google, azure, sarvam, soundfile, silero, webrtc, speechmatics, openrouter, camb, mcp, inworld, smallest, aws-nova-sonic` (`api/Dockerfile`) |
| Other notable deps | `langgraph` + checkpoint tables (AI workflow builder), `fastmcp` (built-in MCP server), `pgvector`, `twilio`, Langfuse, Sentry, PostHog, Prometheus/OpenTelemetry exporter (`api/requirements.txt`) |
| SDKs | `sdk/python`, `sdk/typescript` (generated from OpenAPI, `sdk/codegen`) |
| Deployment | `docker-compose.yaml`: `postgres` (pgvector/pg17), `redis`, `minio`, `nginx`, `coturn` (TURN for WebRTC), `api`, `ui`, optional `cloudflared`. Helm chart in `deploy/helm/dograh` |

## 3. Backend architecture

### 3.1 Entry point and API surface
- `api/app.py`: FastAPI app, prefix `/api/v1`; MCP server mounted at `/api/v1/mcp` (`app.mount`).
  Lifespan starts the ARQ pool, Langfuse exporters, a Redis-based cross-worker sync manager,
  call-event delivery, metrics and event-loop-lag monitors.
- `api/routes/main.py` composes ~30 routers. Largest: `workflow.py` (1,882 lines),
  `organization.py` (1,700), `telephony.py` (1,321), `campaign.py` (1,194), `webrtc_signaling.py` (951).
- Integration-relevant endpoints:

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/public/agent/{uuid}`, `/public/agent/workflow/{workflow_uuid}` (+ `/test/…`) | Trigger calls from outside (`routes/public_agent.py`) |
| `/api/v1/workflow/…` | Workflow CRUD, versions, publish, drafts, runs (`POST /{id}/runs`, `GET /{id}/runs/{run_id}`), reports, templates |
| `/api/v1/telephony/…` | Provider webhooks and call control |
| `/api/v1/ws/…` | WebRTC signalling |
| `/api/v1/agent-stream/{provider}/{workflow_uuid}` | WebSocket for external telephony media streams (`routes/agent_stream.py`) |
| `/api/v1/mcp` | Dograh's own MCP server (coding agents can manage a workspace) |

### 3.2 Authentication and tenancy (`api/services/auth/depends.py`, `api/db/models.py`)
- Three paths: **`X-API-Key`** header (organization API keys, stored as `key_hash` + `key_prefix`,
  `APIKeyModel`); **local email/password** when `AUTH_PROVIDER=local` (OSS default);
  **Stack Auth** in SaaS (team = organization).
- Tenancy: `OrganizationModel` ↔ `UserModel` many-to-many through `organization_users`
  (`user_id`, `organization_id` only). **There are no per-organization roles**, only a global
  `is_superuser` flag. There are **no workspaces inside an organization**.
- Quotas and billing on the organization (`quota_type`, `quota_dograh_tokens`,
  `price_per_second_usd`, `organization_usage_cycles`), plus a call-concurrency service.
- `DEPLOYMENT_MODE` (`oss` default) switches SaaS-only behaviour. In SaaS mode Dograh talks
  to its hosted **MPS** service (`MPS_API_URL=https://services.dograh.com`) for billing
  accounts, signup grants and managed model keys (`services/mps_billing.py`). OSS mode skips it.

### 3.3 Data model (36 tables + `organization_users` association, `api/db/models.py`)
Users, organizations, API keys, org/user configuration stores, provider connections and
named model configurations, telephony configurations/trunks/phone numbers, integrations,
workflows + versioned workflow definitions + folders + templates, workflow runs and text
sessions, campaigns and queued runs, embed tokens/sessions, agent triggers, external
credentials, webhook deliveries, tools, knowledge-base documents and chunks (pgvector),
recordings, usage cycles, LangGraph checkpoint tables and builder runs.

### 3.4 Voice runtime (`api/services/pipecat/`)
- One Pipecat pipeline per call: transport → audio-in filter → VAD/turn strategies → STT
  → LLM (with tools) → TTS → transport. Built by `pipeline_builder.py`, `run_pipeline.py`,
  `service_factory.py`, `transport_setup.py`.
- **Agent bridge** (`agent_bridge.py`, `agent_runtime_factory.py`): call-scoped parts
  (transport, recording, recognition, shared context) stay on the call pipeline. Each
  workflow visit or transfer gets its own agent worker (LLM + TTS). This is a natural seam
  for plugging in other agent runtimes later.
- Turn handling uses Pipecat's `turns.user_start` / `user_stop` strategies (VAD-based and
  transcription-based), Silero VAD (Pipecat extra).
- **Noise reduction** (`services/pipecat/noise_reduction/`): RNNoise over ctypes with a
  vendored `api/native/rnnoise/librnnoise.so` (x86-64), wrapped in a fail-open `SafeAudioFilter`,
  enabled per workflow (`noise_reduction_configuration`), kill switch
  `NOISE_REDUCTION_ENABLED`. Wired into every telephony transport via
  `audio_in_filter=build_audio_in_filter(...)`.
- Dograh's own benchmark (`api/noise_reduction_plan.md`) finds RNNoise **hurts clean or
  lightly noisy speech** and **babble**, and plans an engine picker (Phase 3).
  `api/noise_reduction_custom_model_plan.md` plans a "Krisp-class" model starting from
  DeepFilterNet3. **This is exactly the slot nexora-audio fills** (§6).

### 3.5 Telephony and real-time transport
Providers in `services/telephony/providers/`: **Twilio, Plivo, Vonage, Telnyx, Exotel,
Vobiz, Cloudonix, Asterisk ARI, WhatsApp**, plus SIP/external PBX, inbound routing, call
transfer. WebRTC via Pipecat SmallWebRTC + coturn.

### 3.6 Workflows, tools, knowledge
- Conversation workflows are node graphs (`services/workflow/`, `node_specs/`) executed by
  `pipecat_engine*.py`. Includes variable extraction, dispositions, QA, transfers, human handoff.
- Tools (`services/workflow/tools/`): **custom HTTP tool** (`custom_tool.py`, method/URL
  templating, credential auth, URL safety validation, default timeout 5,000 ms), **MCP tool**
  (`mcp_tool.py`), **knowledge base** (pgvector), calculator, timezone, transfer resolver.
- Integrations (`services/integrations/`): BigQuery, Noveum, Paygent, Tuner.

### 3.7 Observability
Langfuse tracing per organization, Sentry, PostHog product analytics, Prometheus metrics,
event-loop lag gauge, per-call usage metrics.

## 4. Security observations
| # | Observation | Impact for NEXORA |
|---|---|---|
| S1 | `agent-stream` WebSocket authenticates by workflow UUID only (by design, for telephony providers) | Treat workflow UUIDs as secrets; front with provider signature checks where available |
| S2 | `ENABLE_TELEMETRY` defaults to **true** (compose sets it for `api` and `ui`) → PostHog/Sentry | Must default to off for enterprise/on-prem customers |
| S3 | OSS mode CORS `*` without credentials; SaaS requires an explicit allowlist (`app.py`) | Fine behind NEXORA's gateway |
| S4 | No org-level RBAC (only global superuser) | NEXORA Core must own roles/permissions |
| S5 | Custom HTTP tools validate user URLs (`utils/url_security.py`) | Reusable pattern; keep for cross-engine calls |

## 5. Integration points for NEXORA (no Dograh code changes needed)
| Need | Mechanism today |
|---|---|
| Manage agents, versions, runs | REST `/api/v1/workflow/*` with `X-API-Key` |
| Start calls programmatically | `POST /api/v1/public/agent/{uuid}` |
| Voice agent → AI workflow (Dify/graphon) | **Custom HTTP tool** (sync, ≤ timeout) or **MCP tool** → NEXORA Orchestrator |
| Events back to NEXORA | Webhook deliveries (`webhook_deliveries`), call-event delivery |
| Recordings/transcripts | Workflow run + recording endpoints, MinIO |
| Manage Dograh from AI tools | Built-in MCP server `/api/v1/mcp` |

## 6. Where nexora-audio plugs in
Dograh already has the hook (`audio_in_filter`) and the plan (engine picker). nexora-audio
offers DeepFilterNet3 + RNNoise with speech-gated pause cleaning, Silero VAD and turn
events, measured on real speech. Integration = one new engine in
`services/pipecat/noise_reduction/factory.py` wrapping nexora-audio's processors as a
Pipecat `BaseAudioFilter`, selectable per workflow. Its known gap (telephony 8 kHz quality and
babble) matches Dograh's own findings and is the next engine-quality target.

## 7. Gaps NEXORA must fill
Org roles/RBAC, workspaces inside an organization, SSO (SAML/SCIM), unified resource
registry, cross-engine tracing (OpenTelemetry trace propagation into tool calls),
telemetry-off defaults, NEXORA branding (permitted by BSD-2; keep the copyright notice in
`LICENSE`/about page).

## 8. Risks
- **Python 3.13 pin** and a **forked Pipecat**: upgrades must track `dograh-hq/pipecat`.
- Large, fast-moving codebase (release-please, ~98 KB CHANGELOG): pin a version, upgrade deliberately.
- SaaS-only features depend on Dograh's hosted MPS. NEXORA SaaS must replace them
  (billing, managed keys) with its own services or BYOK.
- RNNoise library vendored for x86-64 only (arm64 falls back).

## 9. Verdict
**Use Dograh as NEXORA's voice engine.** Licence allows it, the architecture has clear
seams (agent bridge, tools, audio filter, REST/MCP), and the gaps are platform concerns
NEXORA Core is meant to own anyway.
