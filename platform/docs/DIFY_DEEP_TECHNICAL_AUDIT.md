# Dify: deep technical audit (for NEXORA AI)

| | |
|---|---|
| Source audited | Fork `Sufi1512/dify`, commit `3d364804fca9db45690e42d8e49b7cb90f4bbedf` (2026-11-13), Dify **1.19.0** (`api/pyproject.toml`, image tags) |
| Licence | **Dify Open Source License**: modified Apache 2.0 with extra conditions (`LICENSE`, © 2025 LangGenius) |
| Separately published parts checked | `graphon` 0.8.0 (workflow engine, PyPI wheel inspected): **plain Apache-2.0**. `dify-plugin-daemon`: **Apache-2.0** per its README. `dify-sandbox`: not verified |
| Method | Read of the source tree, models, controllers, compose files; wheel inspection of `graphon`. Not legal advice |

## 1. Licence: what it allows and forbids (read first)
From `LICENSE` in the fork:
1. Commercial use is allowed, "including as a backend service for other applications or as
   an application development platform for enterprises".
2. **Multi-tenant:** "Unless explicitly authorized by Dify in writing, you may not use the
   Dify source code to operate a multi-tenant environment." Tenant = **workspace**.
3. **Logo/copyright:** when using Dify's **frontend** (everything in `web/` or the `web`
   image), the Dify logo and copyright may not be removed or modified. Not applicable to
   backend-only use.
4. "The interactive design of this product is protected by appearance patent." NEXORA's UI
   must be its own design, not a re-skin of Dify's.
5. The producer may change the licence; contributions may be used commercially by LangGenius.

| NEXORA use of Dify | Allowed without a commercial licence? |
|---|---|
| Single-tenant, Dify UI kept with logo (e.g. one install per customer) | Yes. Caveat: several workspaces inside one install may itself count as "multi-tenant". Confirm with LangGenius |
| Dify backend behind NEXORA UI, **one tenant per deployment** | Logo rule doesn't apply; multi-tenant rule still applies per deployment |
| Dify backend serving many NEXORA organizations (shared SaaS) | **No**, needs written authorization |
| Re-branded Dify web console | **No** |
| `graphon` engine (Apache-2.0) inside NEXORA's own services | **Yes**, standard Apache terms (keep NOTICE/licence) |
| `dify-plugin-daemon` (Apache-2.0) | **Yes**, standard Apache terms. Individual plugins carry their own licences |

## 2. Size and stack

| Area | Facts |
|---|---|
| Backend | `api/`: **Flask** 3 + flask-restx, Celery + Redis, SQLAlchemy, gunicorn, Python **~3.13**. ~537k lines of Python, 1,707 test files, 250 migrations. PostgreSQL default (`DB_TYPE=postgresql`); MySQL/OceanBase/SeekDB optional |
| Frontend | `web/`: Next.js + React (pnpm workspace catalog), ~977k lines TS/TSX incl. tests and i18n |
| Workflow engine | External package **`graphon==0.8.0`** (LangGenius, Apache-2.0): graph parsing/validation, queue-based `GraphEngine`, runtime state/variable pool, events, **Dify DSL import (`graphon.dsl.loads`)**, model-runtime abstractions |
| New components | `dify-agent/` (Pydantic AI agent runtime, Python) and `dify-agent-runtime/` (Go). No separate licence file → covered by the root Dify licence |
| Deployment (`docker/docker-compose.yaml`) | `api`, `api_websocket`, `worker`, `worker_beat`, `worker_knowledge_fs_upgrade`, `web`, `db_postgres`/`db_mysql`, `redis`, `sandbox` (dify-sandbox 0.2.15), `local_sandbox`, `plugin_daemon` (0.6.14), `knowledge_fs` + 5 workers, `agent_backend`, `ssrf_proxy` + `agent_ssrf_proxy`, `nginx`, `certbot`, and ~15 selectable vector stores (Weaviate, Qdrant, pgvector, Milvus, OpenSearch, Elasticsearch, Chroma, Oracle, …) |

## 3. Architecture

### 3.1 API surfaces (`api/controllers/`)
| Surface | Who uses it | Auth |
|---|---|---|
| `console` | Dify's own web console | Account login, JWT (`libs/passport.py`, HS256) |
| `web` | End users of published web apps | App/passport tokens |
| `service_api` | **External systems (what NEXORA would call)** | Per-app / per-dataset API keys (`validate_app_token`) |
| `mcp` | MCP clients: **any Dify app can be exposed as an MCP server** (`AppMCPServer`, unique `server_code`) | Server code |
| `trigger`, `inner_api`, `openapi`, `files` | Webhook/schedule triggers, internal calls, OpenAPI, files | Various |

Service API highlights: `/chat-messages`, `/completion-messages` (+ stop), `/workflows/run`,
`/workflows/{id}/run`, `/workflows/run/{run_id}`, `/workflows/tasks/{task_id}/stop`,
`/workflows/logs`, `/conversations/*`, `/audio-to-text`, and a full `/datasets/*` knowledge API
(create docs by file/text, segments, metadata, `retrieve`, RAG pipeline run).

### 3.2 Tenancy and permissions
- `Tenant` = workspace; `Account` ↔ tenant via `TenantAccountJoin` with **roles**
  `owner, admin, editor, normal, dataset_operator` (`enums/account.py`).
- Resource-scoped RBAC entities (`core/rbac/entities.py`): scopes `app, dataset,
  knowledge_space, agent, workspace` with whitelists `all / specific / only_me`.
- Plugin install/debug permissions per tenant.

### 3.3 Runtime (`api/core/`)
- **App modes**: chat, completion, agent chat, advanced chat (chatflow), workflow
  (`core/app/` generators per mode).
- **Workflow**: Dify turns stored graph configs into a `graphon` graph and runs `GraphEngine`.
  graphon ships the generic nodes: `start, end, answer, llm, code, http_request, if_else,
  iteration, loop, question_classifier, parameter_extractor, template_transform,
  variable_aggregator/assigner, list_operator, document_extractor, tool, human_input`.
  Dify adds its own (`core/workflow/nodes/`): `agent`/`agent_v2`, `knowledge_retrieval`,
  `knowledge_index`, `datasource`, `trigger_plugin/schedule/webhook`, `human_input_v2`.
- **RAG** (`core/rag/`): extractors, splitters, embedding, indexing, retrieval, rerank,
  summary index; plus **external knowledge APIs** (`ExternalKnowledgeApis` model) and the
  new `knowledge_fs` services.
- **Models and tools** are delivered as **plugins** run by `plugin_daemon` (Go). Providers
  come from the Dify marketplace, governed by the marketplace agreement and each plugin's licence.
- **MCP**: client (`core/mcp/client`) to use external MCP tools, server (`core/mcp/server`)
  to expose apps.
- Code execution in `dify-sandbox`; outbound HTTP via `ssrf_proxy` (Squid).

## 4. Security observations
| # | Observation | Impact for NEXORA |
|---|---|---|
| S1 | Mature SSRF isolation (`ssrf_proxy`) and code sandbox | Reuse the pattern for NEXORA's own tool calls |
| S2 | Service API keys are per app/dataset, not per user or organization | NEXORA must map its org/workspace permissions onto these keys and never expose them to clients |
| S3 | Heavy service footprint (20+ containers incl. vector store) | Larger attack surface and ops cost; plan per-customer isolation carefully |

## 5. Integration points for NEXORA
| Need | Mechanism |
|---|---|
| Run an AI workflow from a voice call | `POST /v1/workflows/run` (blocking or streaming SSE), app API key |
| Chat/agent app | `POST /v1/chat-messages` |
| Shared knowledge | `/v1/datasets/{id}/retrieve`, or point Dify at a NEXORA Knowledge API via **external knowledge APIs** |
| Zero-code bridge from Dograh | Expose the Dify app as an **MCP server** and attach it in Dograh as an **MCP tool** |
| Run Dify-built workflows without Dify | `graphon.dsl.loads(yaml, credentials=…)` → `GraphEngine.run()` (Apache-2.0) |

## 6. Implications for the NEXORA architecture
The audit changes the plan's licensing picture in a useful way:

1. **Multi-tenant NEXORA SaaS cannot run the Dify application** (api + web) for many
   customers without written authorization from LangGenius, no matter what gateway sits in front.
2. **But the workflow engine is separable and permissively licensed.** `graphon`
   (Apache-2.0) runs Dify-style workflows and imports Dify DSL. `dify-plugin-daemon`
   (Apache-2.0) runs model/tool plugins. NEXORA can build its **own AI engine** on these,
   with NEXORA-owned RAG/knowledge (Dograh already has pgvector RAG), NEXORA-owned APIs
   and a NEXORA-designed UI. That way it does not depend on the restricted Dify application code.
3. What you lose without the Dify app: its console/builders, app modes, RAG pipelines,
   knowledge_fs, agent runtime, annotation/feedback features and 250 migrations of product
   behaviour. NEXORA would rebuild the builder UI (its own design) on top of graphon.

| Option | Licence position | Effort | Recommended for |
|---|---|---|---|
| A. Commercial licence from LangGenius, run Dify app as AI engine | Clean once signed | Lowest engineering | Fastest path to the plan as written |
| B. Single-tenant Dify per customer (on-prem/private cloud) | Likely OK. Confirm the multi-workspace question | Medium (per-customer ops) | Enterprise on-prem deals |
| C. **NEXORA AI engine on graphon + plugin daemon** (Apache-2.0) | Clean, no Dify app code | Highest (own builder UI, RAG, app layer) | Long-term multi-tenant SaaS |

Recommended: **pursue A in parallel with building C.** Start Option C's engine adapter so
NEXORA never hard-depends on the restricted code. Use B for early enterprise customers
who want Dify's UI on their own infrastructure.

## 7. Risks
- Licence can be tightened by the producer (clause 2a). Pin versions and keep legal review current.
- Very large, fast-moving codebase (1.19.0, frequent releases). Forking it is costly to maintain.
- `graphon` is young (0.x, API may change), and its Slim LLM runtime assumes the plugin daemon.
- Plugins/marketplace content each carry their own licence. Audit before bundling.
- Python 3.13 in both Dify and Dograh: aligned, but both pin tightly.

## 8. Verdict
Dify's **application** is a strong engine but **its licence blocks the plan's core
business model** (branded, multi-tenant SaaS) unless LangGenius authorizes it. Dify's
**engine layer** (`graphon`, plugin daemon) is permissively licensed and is the safer
foundation for NEXORA's AI engine.
