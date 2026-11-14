# NEXORA AI: integration specification

| | |
|---|---|
| Status | Draft for approval (document 5 of 6) |
| Scope | How NEXORA talks to Dograh, the Dify app and the graphon runtime; the cross-engine tool-call contract; engine events; tracing; reconciliation |
| Verification rule | Engine endpoints listed here come from the two audits. Request/response field shapes marked **VERIFY** must be confirmed against the pinned engine version (OpenAPI for Dograh, `api/controllers/service_api` for Dify) before the adapter ticket is closed |

## 1. Adapter layer

The Integration Gateway (`services/core/engines/`) exposes typed, capability-split
interfaces. The orchestrator and API code only use these. Engine HTTP details never
leak above the adapter.

```python
from typing import Protocol, AsyncIterator

class VoiceEngine(Protocol):
    capabilities: frozenset[str]
    # provisioning
    async def provision_account(self, ws: WorkspaceRef) -> EngineAccount: ...
    async def health(self) -> EngineHealth: ...
    # agents (Dograh "workflows")
    async def create_agent(self, acct: EngineAccount, spec: VoiceAgentSpec) -> EngineObjectRef: ...
    async def get_agent(self, acct: EngineAccount, ref: str) -> VoiceAgent: ...
    async def update_agent(self, acct: EngineAccount, ref: str, spec: VoiceAgentSpec) -> VoiceAgent: ...
    async def publish_agent(self, acct: EngineAccount, ref: str) -> EngineVersionRef: ...
    async def delete_agent(self, acct: EngineAccount, ref: str) -> None: ...
    async def list_agents(self, acct: EngineAccount, cursor: str | None) -> Page[VoiceAgent]: ...
    # calls / runs
    async def start_call(self, acct: EngineAccount, ref: str, req: StartCallRequest) -> CallRef: ...
    async def get_run(self, acct: EngineAccount, ref: str, run_id: str) -> VoiceRun: ...
    # tools pointing back at NEXORA
    async def upsert_tool(self, acct: EngineAccount, tool: NexoraToolSpec) -> EngineObjectRef: ...
    # model credentials
    async def apply_model_config(self, acct: EngineAccount, cfg: ModelConfigView) -> None: ...

class AIEngine(Protocol):
    capabilities: frozenset[str]
    async def provision_account(self, ws: WorkspaceRef) -> EngineAccount: ...
    async def health(self) -> EngineHealth: ...
    async def create_workflow(self, acct: EngineAccount, spec: WorkflowSpec) -> EngineObjectRef: ...
    async def import_dsl(self, acct: EngineAccount, dsl_yaml: str) -> EngineObjectRef: ...   # cap: dsl.import
    async def run_workflow(self, acct: EngineAccount, ref: str, inputs: dict,
                           *, deadline_ms: int, run_ctx: RunContext) -> RunResult: ...
    def stream_workflow(self, acct: EngineAccount, ref: str, inputs: dict,
                        *, run_ctx: RunContext) -> AsyncIterator[RunEvent]: ...          # cap: workflow.run.streaming
    async def get_run(self, acct: EngineAccount, ref: str, run_id: str) -> RunResult: ...
    async def stop_run(self, acct: EngineAccount, ref: str, task_id: str) -> None: ...
    async def chat(self, acct: EngineAccount, ref: str, msg: ChatRequest,
                   *, run_ctx: RunContext) -> AsyncIterator[ChatEvent]: ...               # cap: chat
    async def apply_model_config(self, acct: EngineAccount, cfg: ModelConfigView) -> None: ...

class KnowledgeBackend(Protocol):
    async def create_base(self, kb: KnowledgeBaseSpec) -> str: ...
    async def add_document(self, kb_id: str, doc: DocumentInput) -> str: ...
    async def delete_document(self, kb_id: str, doc_id: str) -> None: ...
    async def retrieve(self, kb_id: str, query: str, opts: RetrievalOptions) -> list[Chunk]: ...
```

`RunContext` carries `organization_id`, `workspace_id`, `execution_id`,
`traceparent`, `idempotency_key` and `deadline`. Every adapter call gets it.

Implementations: `DograhVoiceEngine`, `DifyAppEngine`, `GraphonEngine`,
`PgvectorKnowledge`, `DifyDatasetKnowledge`. Adapter selection comes from
`engine_accounts` for the workspace (DB doc §3.3).

## 2. Dograh adapter

| Setting | Value |
|---|---|
| Base URL | `http://<dograh-api>:<port>/api/v1` on the private network (port per pinned `docker-compose.yaml`, **VERIFY**) |
| Auth | `X-API-Key: <Dograh org API key>` from `engine_accounts.credential_secret_id` |
| Mode | `DEPLOYMENT_MODE=oss`, `ENABLE_TELEMETRY=false` |

### 2.1 Operation mapping
| NEXORA operation | Dograh mechanism (audit §3.1, §5) | Notes |
|---|---|---|
| `provision_account` | Create organization + org API key | **VERIFY**: Dograh routes in `routes/organization.py`. If an org-creation API usable with a service credential is missing, NEXORA uses a Dograh superuser account (`is_superuser`) held only by the Integration Gateway. Fallback: a one-file Dograh patch adding a provisioning endpoint |
| `create_agent` / `update_agent` | `/api/v1/workflow/*` CRUD + drafts | Workflow definition JSON follows Dograh `node_specs/`. **VERIFY** schema per pinned version |
| `publish_agent` | `/api/v1/workflow/*` publish / versions | Store the returned version in `resource_versions.engine_version_ref` |
| `start_call` | `POST /api/v1/public/agent/{uuid}` or `/public/agent/workflow/{workflow_uuid}` | Use the `/test/…` variants for portal "test call" |
| `get_run` | `GET /api/v1/workflow/{id}/runs/{run_id}` | Transcript, extracted variables, disposition, usage |
| Web test session | `/api/v1/ws/…` WebRTC signalling | Portal gets a short-lived NEXORA-issued token. The Dograh signalling path is proxied by the gateway |
| `upsert_tool` | Dograh tools API (custom HTTP tool / MCP tool) | See §4 |
| `apply_model_config` | Dograh provider connections + named model configurations | **VERIFY** endpoints |
| Events | Dograh webhooks / call-event delivery → `POST /internal/v1/engine-events/dograh/{engine_account_id}` | See §6 |
| Noise reduction | Per-workflow `noise_reduction_configuration` | Value `nexora_dfn3` once the nexora-audio engine is added to the Dograh fork |

### 2.2 Security notes
- `agent-stream` WebSocket authenticates with the workflow UUID only (audit S1). NEXORA
  never shows workflow UUIDs to users. Provider media URLs are set by NEXORA
  provisioning, and UUIDs are rotated (republish as a new workflow) if one leaks.
- Telephony provider webhooks reach Dograh through the edge with provider signature
  validation where the provider supports it (Twilio, Plivo, Vonage, Telnyx).

## 3. AI engine adapters

### 3.1 DifyAppEngine (dedicated installations only)
| Setting | Value |
|---|---|
| Base URL | `http://<dify-api>/v1` (Service API, behind the install's nginx) inside the customer's dedicated environment |
| Auth | Per-app API key (`Authorization: Bearer app-…`) and per-dataset key, from `resources.engine_secret_id` / `knowledge_bases` |
| Guard | Adapter refuses to start if `engine_instances.tenancy != 'dedicated'` |

| NEXORA operation | Dify Service API (audit §3.1, §5) |
|---|---|
| `run_workflow` blocking | `POST /v1/workflows/run` (`response_mode: blocking`) or `/v1/workflows/{id}/run` for a specific version |
| `stream_workflow` | Same with `response_mode: streaming` (SSE) |
| `get_run` | `GET /v1/workflows/run/{run_id}` |
| `stop_run` | `POST /v1/workflows/tasks/{task_id}/stop` |
| `chat` | `POST /v1/chat-messages` (+ `/conversations/*`) |
| Logs | `GET /v1/workflows/logs` |
| Knowledge (DifyDatasetKnowledge) | `/v1/datasets/*`: create document by file/text, segments, metadata, `/datasets/{id}/retrieve` |
| `create_workflow`, `import_dsl` | **Not in the Service API.** Done through Dify's console API with a NEXORA service account in that installation. **VERIFY** before relying on it. Otherwise app creation is a manual step in the dedicated install, and NEXORA registers the app by API key |
| Zero-code bridge | Dify app exposed as MCP server (`AppMCPServer`), attached to Dograh as an MCP tool |

### 3.2 GraphonEngine (NEXORA AI Runtime, shared SaaS)
The runtime is a NEXORA service, so its API is NEXORA's to define:

| Endpoint (internal, proposed) | Purpose |
|---|---|
| `POST /internal/v1/workflows` | Store workflow graph (NEXORA JSON, convertible to and from Dify DSL) |
| `POST /internal/v1/workflows/import-dsl` | `graphon.dsl.loads(yaml, credentials=…)` |
| `POST /internal/v1/workflows/{id}/runs` | Run (`mode=blocking|stream|async`) |
| `GET /internal/v1/runs/{run_id}` | Status, outputs, node events |
| `POST /internal/v1/runs/{run_id}/cancel` | Cancel |

Implementation notes:
- Runs `GraphEngine` in worker processes. Per-run limits: wall clock, node count, LLM
  token budget, memory.
- Credentials are injected at run time from Model Hub (`secrets`), scoped to the
  workspace. They are never stored in the graph.
- Node set: graphon generic nodes (`start, end, answer, llm, code, http_request,
  if_else, iteration, loop, question_classifier, parameter_extractor,
  template_transform, variable_aggregator/assigner, list_operator,
  document_extractor, tool, human_input`) + NEXORA nodes `nexora_knowledge_retrieval`,
  `nexora_agent`, `nexora_voice_handoff`, `nexora_approval`.
- DSL import maps Dify-only nodes (`knowledge_retrieval`, `agent`, `datasource`,
  triggers) to NEXORA equivalents or fails with a list of unsupported nodes.

## 4. Cross-engine tool-call contract (Dograh → NEXORA)

### 4.1 How it is installed
When a user links a voice agent to an AI workflow or knowledge base in the portal,
NEXORA:
1. creates a `tool_bindings` row with a signing secret,
2. calls `VoiceEngine.upsert_tool` to create a Dograh **custom HTTP tool** on that agent:
   - method `POST`, URL `https://<internal-orchestrator>/internal/v1/tool-calls/{binding_id}`
   - headers `X-Nexora-Signature` (HMAC template, **VERIFY** Dograh header templating),
     `X-Nexora-Call-Id: {{call_id}}`
   - timeout 5,000 ms (Dograh default), parameters schema = the target's input schema,
3. records a `resource_links` edge (`uses_workflow` / `uses_knowledge`).

The alternative installation exposes the same targets through **one NEXORA MCP server
per workspace** (`/internal/v1/mcp/{workspace_id}`), attached in Dograh as an MCP tool.
This is used when an agent needs many targets.

### 4.2 Request
```json
POST /internal/v1/tool-calls/tb_3f9a…
X-Nexora-Signature: t=1763050000,v1=hex(hmac_sha256(secret, t + "." + body))
Content-Type: application/json

{
  "call_id": "dograh-run-or-call-id",
  "arguments": { "policy_number": "PN-88213" },
  "context": { "caller_number": "+9665…", "language": "en" }
}
```
Rejected when the signature is wrong, the timestamp is more than 5 minutes old, or the
binding is disabled. The idempotency key is `binding_id + call_id + sha256(arguments)`.

### 4.3 Response (always HTTP 200 to Dograh, so the LLM can speak a result)
```json
{ "status": "ok", "result": { "coverage": "active", "renewal_date": "2027-02-01" },
  "say": "Your policy is active and renews on the first of February." }
```
```json
{ "status": "pending", "execution_id": "exe_…",
  "say": "Let me check that, it will take a moment." }
```
```json
{ "status": "error", "code": "not_authorized",
  "say": "I can't access that information right now." }
```

### 4.4 Timing rules
| Mode | Behaviour |
|---|---|
| `sync` | Run with `deadline_ms` (default 3,500, max 4,500). On timeout cancel the run and return `error` / `timeout` |
| `sync_then_async` | Same deadline, but on timeout keep running and return `pending`. The agent gets a companion tool `get_result(execution_id)` to poll on its next turn |
| `async` | Return `pending` at once. The result is delivered as a webhook or post-call action |

Circuit breaker per target: open after 5 failures in 30 s, half-open after 30 s.
While open, the binding returns `error` immediately so calls don't stall.

## 5. Error model
Adapters map engine errors to one NEXORA error shape, used in the API and stored on
`executions.error`:

```json
{ "code": "engine_timeout", "message": "AI workflow did not finish within 3500 ms",
  "engine": "graphon", "engine_code": null, "retryable": true, "execution_id": "exe_…" }
```

| code | Typical source | Retry |
|---|---|---|
| `engine_unavailable` | Connection refused / 5xx | Yes (exponential, 3 tries, never for voice-sync) |
| `engine_timeout` | Deadline passed | Depends on mode |
| `engine_rejected` | 4xx validation | No |
| `not_found` | Missing engine object (triggers reconciliation) | No |
| `quota_exceeded` | NEXORA quota or engine quota | No |
| `not_authorized` | NEXORA authz or tool grant | No |
| `capability_unsupported` | Adapter lacks capability | No |
| `approval_required` | Sensitive tool | Waits |

## 6. Engine events and reconciliation

### 6.1 Inbound events
`POST /internal/v1/engine-events/{implementation}/{engine_account_id}`, authenticated
by a per-account secret. Steps: store in `engine_inbound_events` (dedupe), ack 2xx
quickly, process in a job.

| Engine event | NEXORA effect |
|---|---|
| Dograh call/run completed | Update execution (if NEXORA started it) or create a `voice_call` execution; usage events (voice minutes, STT/TTS, tokens); customer webhook `voice.call.completed` |
| Dograh run failed | Execution failed + alert counter |
| Dify / graphon run finished | Execution update; token usage events |

### 6.2 Writes: outbox + reconciliation
Creating a resource:
1. Transaction: insert `resources` (status `provisioning`) + `outbox` event.
2. Worker: call the engine adapter, store `engine_resource_id`, set status `active`.
3. On failure: retry with backoff. After the retry limit, status `error` with the reason shown in the portal.

Reconciler job (every 5 minutes per engine account): list engine objects, compare with
the registry, mark registry rows whose engine object vanished as `error`, report engine
objects with no registry row (created outside NEXORA) as "unmanaged" for an admin to import or delete.

## 7. Model Hub propagation
A `model_configs` change produces an outbox event. Workers call
`apply_model_config` on every engine account in scope. Dograh: provider connection +
named model configuration. Dify dedicated: plugin credential for the workspace.
graphon: nothing to push (credentials resolved per run). The portal shows propagation
status per engine.

Streaming and latency: engines call providers directly with the propagated
credentials. NEXORA does **not** proxy model traffic in the first release.

## 8. Tracing
| Hop | Propagation |
|---|---|
| Portal / API → Core | `traceparent` created at the gateway |
| Core → AI engine | `traceparent` header (graphon: native OTel spans; Dify: header logged, run id recorded) |
| Core → Dograh | Header on REST calls; Dograh spans go to Langfuse, linked by run id |
| Dograh → NEXORA tool call | Dograh does not propagate `traceparent` (**VERIFY**), so NEXORA starts a span with `call_id` as a link attribute and stores it on the execution |

Trace view in the portal is built from `executions` + `execution_steps` (always
available) plus OTel spans where present.

## 9. NEXORA public API (first release, proposed)
Base `https://api.nexora.ai/v1`, workspace in path, `Authorization: Bearer nx_…` or
session cookie, `Idempotency-Key` honoured on all `POST`s.

| Area | Endpoints |
|---|---|
| Orgs / workspaces | `GET /organizations/me`, `GET,POST /workspaces`, `GET,PATCH /workspaces/{ws}` |
| Members | `GET,POST /workspaces/{ws}/members`, `PATCH,DELETE …/{member_id}`, `POST /invitations` |
| Voice agents | `GET,POST /workspaces/{ws}/voice-agents`, `GET,PATCH,DELETE …/{id}`, `POST …/{id}/publish`, `POST …/{id}/calls`, `GET …/{id}/calls/{call_id}` |
| AI workflows | `GET,POST /workspaces/{ws}/workflows`, `POST …/{id}/runs`, `GET …/runs/{exe_id}`, `POST …/runs/{exe_id}/cancel`, `POST /workspaces/{ws}/workflows/import-dsl` |
| Links | `POST /workspaces/{ws}/voice-agents/{id}/tools` (creates tool binding) |
| Knowledge | `GET,POST /workspaces/{ws}/knowledge-bases`, `POST …/{id}/documents`, `POST …/{id}/retrieve` |
| Models | `GET,POST /model-providers`, `GET,POST /model-configs` |
| Integrations | `GET,POST /integrations`, `POST /integrations/{id}/tool-grants` |
| Executions | `GET /workspaces/{ws}/executions`, `GET …/{exe_id}` |
| Usage | `GET /usage?from=&to=&group_by=` |
| Developer | `GET,POST,DELETE /api-keys`, `GET,POST /webhook-endpoints` |
| Admin | `GET /audit-logs` |

## 10. Acceptance criteria
1. Each adapter passes a shared contract-test suite against a live pinned engine in CI
   (create → get → run → delete), and every **VERIFY** item is resolved in the test code.
2. A voice test call that invokes a linked AI workflow returns the spoken result, and the
   execution shows both the Dograh call id and the AI run id under one `trace_id`.
3. Forcing the AI engine to sleep past the deadline gives `pending` (or `timeout`) to
   Dograh within 4.5 s, and the call continues.
4. A duplicated Dograh event creates exactly one execution update and one set of usage events.
5. Deleting a Dograh workflow outside NEXORA is detected by the reconciler within one cycle.
6. `DifyAppEngine` refuses to run against an engine instance with `tenancy = shared`.

## 11. Knowledge (RAG)

One NEXORA **Knowledge API** serves voice agents, AI agents, workflows and the public API.
Engine knowledge features are not the shared store (Architecture §6).

### 11.1 Back ends
| Deployment | Store | Notes |
|---|---|---|
| Shared SaaS | PostgreSQL + pgvector (`documents`, `document_chunks`, DB doc §3.6) | Every row carries `organization_id`; row-level security on |
| Dedicated | Same, or `DifyDatasetKnowledge` over Dify `/v1/datasets/*` | Same Knowledge API either way |

Each knowledge base is fixed to one multilingual embedding model. Changing it means a full reindex.

### 11.2 Ingestion pipeline (background jobs, `ingestion_jobs`)
1. **Fetch**: upload, URL crawl (sitemap, re-crawl schedule), API push. Connectors (SharePoint, Drive) later.
2. **Detect**: MIME type and language; route to a parser (§11.3).
3. **Parse** to one internal document model: headings, paragraphs, lists, tables, figures, page numbers, reading order.
4. **Quality check per page**: too little text, broken table, mixed reading order → page flagged, second parser tried, best result kept.
5. **Normalise text**: Unicode NFKC; Arabic: remove diacritics and tatweel for the search copy (original kept for display), unify alef and yaa forms, keep Arabic/English mixing.
6. **Chunk** (§11.4), **enrich** (figures §11.6), **embed**, **index** (vector + full-text).
7. **Version**: checksum per document; only changed documents are re-embedded; previous version kept until the new one is ready.

### 11.3 Parsers
One `DocumentParser` interface; parsers are adapters.

| Parser | Licence | Used for |
|---|---|---|
| **Docling** (primary) | MIT | PDF (digital and scanned), DOCX, PPTX, XLSX, HTML, images. Layout model, TableFormer tables, reading order, figures |
| **Unstructured** open-source library (secondary) | Apache-2.0 | EML/MSG email, EPUB, RTF, ODT and other long-tail formats; second attempt on pages that fail Docling's quality check |
| Arabic-capable OCR engine | To pick in K1 benchmark | Scanned Arabic pages. Docling's Arabic VLM support is experimental, so not relied on alone |
| Own STT (nexora-audio pipeline) | Ours | Audio and video files, chunked by timestamp |

Not used: PyMuPDF (AGPL-3.0), Marker (GPL-3.0), MinerU (custom licence with revenue thresholds and attribution), and Unstructured's hosted API by default (data leaves the deployment; opt-in only for customers who allow it).

### 11.4 Chunking (ours, parser-independent)
- Split on structure: section → paragraph group; tables and figures are their own chunks.
- Target 200–400 tokens per search chunk, counted with the embedding model's tokenizer; overlap 10–15 % within a section only.
- **Parent–child**: search matches small chunks; the parent section (up to ~1,500 tokens) goes to the model.
- **Context prefix** stored and embedded with each chunk: `document title > section path`.
- Metadata on every chunk: `document_id`, version, page, section path, language, source URL, created/updated date, access tags.

### 11.5 Tables and spreadsheets
| Case | Handling |
|---|---|
| Small table (≤ ~30 rows) | One chunk, Markdown |
| Large table | Row groups with the header repeated, plus one sentence per row ("Column: value; …") for row-level questions. JSON copy kept for exact read-back |
| Text-heavy sheet (FAQ, price list) | One chunk per row with sheet name and headers |
| Number-heavy sheet | Loaded into a per-knowledge-base, sandboxed DuckDB file. Agents get a read-only `query_table` tool (text-to-SQL, SELECT only, row and time limits). Formulas read as calculated values; hidden sheets skipped unless enabled; merged header cells flattened |

### 11.6 Images, charts, scans
- Figures stored in object storage, linked to page and position.
- OCR text of the figure + a short vision-model description are indexed with the figure chunk.
- Charts: description includes key values, labelled approximate.
- Chat answers may show the image; voice answers speak only the description.

### 11.7 Retrieval
1. Query rewrite (call transcripts → clean query; keep numbers and IDs verbatim).
2. Permission and metadata filters applied **before** search.
3. Hybrid: PostgreSQL full-text (BM25-style) + vector (HNSW), merged by reciprocal rank fusion.
4. Rerank top 20–40 with a cross-encoder or reranking model; keep 3–6; minimum score, else return `no_answer`.
5. Return chunks with citations (document, page, section, passage offsets).

API (proposed): `POST /v1/workspaces/{ws}/knowledge-bases/{id}/retrieve`
`{ "query", "top_k", "filters", "mode": "chat|voice", "deadline_ms" }` →
`{ "chunks": [{ "text", "score", "citation": {...} }], "no_answer": false, "timing_ms": {...} }`.

### 11.8 Voice mode
- Deadline from the tool binding (default retrieval budget 800 ms inside the 3.5 s tool budget).
- Cache popular queries per knowledge base (keyed by normalised query + filters + KB version).
- Prefetch: a binding may declare a prefetch query run as soon as its inputs are known (for example after the policy number is collected).
- Answers for voice are one or two sentences; citations go to the trace, not the audio.

### 11.9 Evaluation
- Per knowledge base: a test set of questions with expected passages. Metrics: hit rate at k, mean reciprocal rank, `no_answer` precision.
- Runs before reindexing, embedding-model change or parser upgrade; blocks the change on a drop beyond a set threshold.
- Answers marked wrong in calls or chats become new test questions.
- Monitoring: failed ingestion jobs, outdated documents, questions that keep returning `no_answer`.

### 11.10 Acceptance criteria
1. A user can only retrieve chunks from knowledge bases and documents they are allowed to read (negative test across organizations and access tags).
2. A 40-page PDF with tables and figures ingests with tables intact (row and column counts match the source) and figures described.
3. A number-heavy XLSX answers an aggregate question correctly through `query_table`, and a write statement is rejected.
4. Voice-mode retrieval returns within its deadline, or returns `no_answer` with `timing_ms`, never later.
5. Changing the embedding model on a knowledge base runs the test set and reports metrics before switching.
6. Arabic queries with and without diacritics return the same top results.
