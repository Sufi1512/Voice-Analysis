# Workflow Runner (NEXORA AI Runtime): specification

Status: **draft, waiting for approval** (no implementation before approval)   ·   Date: 2026-11-14

Builds on: `NEXORA_SYSTEM_ARCHITECTURE.md` §3.1 and §4.2; `NEXORA_INTEGRATION_SPECIFICATION.md`
§3.2 and §4; `DIFY_DEEP_TECHNICAL_AUDIT.md` (graphon 0.8.0, plugin daemon); roadmap P3.

## Problem and goal
NEXORA's shared cloud cannot run the Dify application without written permission from LangGenius.
The Workflow Runner runs AI workflows on **graphon** (Apache-2.0) instead, so NEXORA owns the
runtime. Success: a workflow built in the NEXORA builder or imported from a Dify DSL file runs
blocking and streaming, with per-workspace credentials, inside the 3.5 s answer budget a voice
call allows for short workflows.

## Scope
### In scope
- `platform/services/ai-runtime/`: a separate service, Python 3.13, `graphon` pinned to 0.8.0.
- Internal API (proposed): `POST /internal/v1/workflows`, `POST /internal/v1/workflows/import-dsl`,
  `POST /internal/v1/workflows/{id}/runs` (`mode`: `blocking` | `stream` | `async`),
  `GET /internal/v1/runs/{run_id}`, `POST /internal/v1/runs/{run_id}/cancel`.
- Workers running graphon's `GraphEngine`; per-run limits: wall clock, node count, LLM token budget, memory.
- Model and tool plugins through `dify-plugin-daemon` (Apache-2.0), each plugin's licence checked before bundling.
- Credentials injected per run from NEXORA Core's secrets, scoped to the workspace; never stored in the graph.
- Generic graphon nodes, plus NEXORA nodes: `nexora_knowledge_retrieval`, `nexora_agent` (tool-calling loop),
  `nexora_approval`, `nexora_voice_handoff` (return to call).
- Dify DSL import with a report of unsupported nodes (Dify-licensed ones: `knowledge_retrieval`, `agent`, `datasource`, triggers).
- Code node in a separate sandboxed container, no network by default (Dify's sandbox licence is unverified, so not reused).
- Outbound HTTP through an egress proxy with SSRF rules.
- Run events and timings for NEXORA's execution trace (`executions`, `execution_steps`).

### Out of scope
- The NEXORA builder UI (P3, separate spec), knowledge ingestion (Phase PK), any Dify application code.

## Behaviour
1. Core calls the runner with a workflow, inputs and a `RunContext` (organization, workspace, execution id, traceparent, deadline).
2. The runner resolves credentials, starts `GraphEngine`, emits node events, returns outputs (blocking) or streams them.
3. Past the deadline: `blocking` cancels and returns `timeout`; the cross-engine contract's `sync_then_async` keeps running and returns `pending`.
4. Cancel stops the run within 1 s.
Errors map to NEXORA's error model (`engine_timeout`, `engine_rejected`, `quota_exceeded`, `capability_unsupported`).

## Acceptance criteria
- [ ] AC-1 A sample workflow (start → LLM → end) runs blocking and streaming against a stub model provider.
- [ ] AC-2 Two workspaces with different provider keys run the same workflow concurrently; neither sees the other's key (test inspects requests at the stub).
- [ ] AC-3 A Dify DSL file with supported nodes imports and runs; one with unsupported nodes is rejected with the list of node types.
- [ ] AC-4 A workflow exceeding wall clock, node count or token budget stops with the matching error.
- [ ] AC-5 A short workflow (3 nodes, stub model 200 ms) answers blocking in under 1 s at p95 on CI runners; cancel takes effect within 1 s.
- [ ] AC-6 The code node cannot reach the network or read the host filesystem (tests try both).
- [ ] AC-7 An HTTP node is refused for private, loopback and metadata addresses.
- [ ] AC-8 No module from the Dify application is imported (static check in CI).

## Open questions
1. Is LangGenius's answer awaited before P3 starts, or does the runner proceed regardless (proposed: proceed; it is needed in every case for the shared cloud)?
2. Which model plugins to bundle first (proposed: OpenAI, Anthropic, Gemini, an OpenAI-compatible endpoint).
3. Sandbox technology for the code node (gVisor, Firecracker or a locked-down container).
