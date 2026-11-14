# NEXORA AI: feature catalogue

| | |
|---|---|
| Status | Draft for approval, 2026-11-14 |
| Companion docs | `NEXORA_PRODUCT_PLAN.md` (modules), `NEXORA_IMPLEMENTATION_ROADMAP.md` (tickets), `NEXORA_INTEGRATION_SPECIFICATION.md` §11 (Knowledge) |
| Design | Signal Room canvas: https://claude.ai/artifact/9w5bzWzzctRNkfz7b7ESzD (tokens, colour and motion, dashboard, voice agent editor, AI workflow builder, execution trace, analytics, members) |

Each feature is tagged:

- **Standard**: expected of any voice or AI platform. Needed to compete, not a reason to choose NEXORA.
- **Unique**: a NEXORA differentiator, because of the cross-engine design, our own audio layer, or governance. Competitor notes are as checked on 2026-11-14 and must be re-checked before marketing.

Release = roadmap release (R1 to R6).

## 1. Differentiators

| # | Feature | What the user gets | Why others can't easily copy it | Release |
|---|---|---|---|---|
| U1 | **Self-healing agents** | Failed and transferred calls are grouped by cause. NEXORA proposes a fix to the flow or prompt, turns those real calls into a test set, then rolls the fix out to a share of traffic and reports the result | Simulation (Vapi Simulations, Retell), replay and A/B testing (Cekura, Hamming) exist as separate tools. One closed loop inside the builder, across voice and AI steps, does not | R5 |
| U2 | **Audio quality as a feature** | Per-call audio score (noise, echo, background talkers, packet loss, clipping, end-of-turn accuracy). The trace answers "was the caller misheard or did the AI misunderstand?" | Uses nexora-audio's own processing (noise removal, echo cancellation, background-talker gate, packet-loss concealment, Smart Turn). Platforms renting audio from providers cannot measure inside it | R2 to R4 |
| U3 | **One agent, every channel** | The same agent (workflows, knowledge, tools, guardrails) answers phone, web chat, WhatsApp and the API. Changes publish to all channels at once | Needs voice and AI engines behind one registry and one tool layer, which is NEXORA's core design | R4 to R5 |
| U4 | **Live answer budget** | Every call has a time budget. A slow backend triggers a holding line, the work keeps running, and the answer is picked up on the next turn. The trace shows where the time went | Cross-engine orchestrator with deadlines, `sync_then_async` mode and companion `get_result` tool (Integration spec §4) | R4 |
| U5 | **Supervisor takeover** | A supervisor can listen, whisper to the AI, take over the call and hand it back. The AI keeps the full conversation context | Needs control of the voice pipeline and the agent state together | R5 |
| U6 | **Mid-call approvals and governance** | The AI prepares a refund or payment, a person approves it during the call. Personal data masked by role, hash-chained audit log, per-tool permissions | Approvals and tool grants are first-class objects in NEXORA Core, not add-ons | R4 to R6 |
| U7 | **Bring your own agent** | Customers keep their existing bot and connect it over a WebSocket. NEXORA adds audio processing, monitoring, analytics and governance around it | nexora-server already accepts customer WebSockets and agent platforms | R5 |
| U8 | **Cost per resolved call** | Live cost meter per call. Model routing picks a faster or cheaper model to stay inside the latency budget. Reports cost per outcome, not just per minute | Usage is attributed per execution across both engines (DB doc §3.8) | R5 |
| U9 | **Arabic done differently** | NEXORA does not train its own Arabic speech models. It plugs in the best ones, routes each call by dialect, handles Arabic and English mixed in one sentence, runs fully in-Kingdom or on-premises. Portal has right-to-left layout and Hijri dates | The Saudi Arabic voice market is crowded (Ziwo, Hamsa with OmniOps, Nabrah, Arabic.AI). NEXORA competes as the orchestration and governance layer over them, not as another model | R2 to R6 |
| U10 | **Structured knowledge** | Spreadsheets with numbers become queryable tables. Agents answer "how many claims in March" with a read-only query, not a guess from text search | Knowledge §11.5. Most platforms only embed text chunks | R5 |

Recommended core story for the first launch: **U1, U2, U4 and U6**.

## 2. Full catalogue by module

### 2.1 Dashboard (R1)
| Feature | Tag |
|---|---|
| Counts of voice agents, AI agents, workflows, live calls | Standard |
| Usage: voice minutes, LLM tokens, API requests, failed runs | Standard |
| System health per engine and dependency | Standard |
| Live now panel with signal lanes per call (voice amber, AI lilac) | Unique (U4 visual) |
| Audio quality summary across calls | Unique (U2) |

### 2.2 Voice AI Studio (R2)
| Feature | Tag |
|---|---|
| Create, edit, version and publish voice agents | Standard |
| Voice flow builder (Dograh node specs) | Standard |
| STT, TTS and LLM choice per agent, language and voice | Standard |
| Inbound and outbound calls, phone numbers, campaigns | Standard |
| Browser test call with live transcript and timings | Standard |
| Recordings, transcripts, extracted fields, call history | Standard |
| Handoff to a person with call summary | Standard |
| nexora-audio processing per agent (noise, echo, background talkers, turn detection) | Unique (U2) |
| Per-call audio quality score and "misheard or misunderstood" view | Unique (U2) |
| Supervisor listen, whisper, take over, hand back | Unique (U5) |
| Dialect routing and Arabic/English mixing | Unique (U9) |

### 2.3 AI Agent Studio (R3)
| Feature | Tag |
|---|---|
| Agents with instructions, model, tools, memory and knowledge | Standard |
| Preview chat, run history, versions | Standard |
| Same agent published to phone, chat, WhatsApp and API | Unique (U3) |
| Tool permissions per agent, approval for sensitive tools | Unique (U6) |

### 2.4 Workflow Studio (R3)
| Feature | Tag |
|---|---|
| Visual AI workflow builder (React Flow, graphon node schema) | Standard |
| Test run with live node status and timings | Standard |
| Import Dify workflows (DSL) | Standard |
| Approval step that pauses for a person | Unique (U6) |
| Return-to-call step with spoken answer template | Unique (U4) |

### 2.5 Cross-engine orchestration (R4)
| Feature | Tag |
|---|---|
| Voice agent calls an AI workflow or knowledge base mid-call | Unique |
| Answer budget, holding line, continue in background | Unique (U4) |
| One trace across both engines | Unique |

### 2.6 Knowledge Hub (R5)
| Feature | Tag |
|---|---|
| Upload PDF, Word, PowerPoint, Excel, text, Markdown, HTML, images; crawl websites | Standard |
| Hybrid search, reranking, citations | Standard |
| Structure-aware chunking with tables and figures kept intact | Standard, done well |
| Chunk preview and per-page fixes | Standard |
| One knowledge base shared by voice and AI agents | Unique (U3) |
| Spreadsheets as queryable tables | Unique (U10) |
| Voice-latency retrieval (deadline, cache, prefetch, short spoken answers) | Unique (U4) |
| Arabic normalisation and Arabic OCR | Unique (U9) |
| Retrieval tests and feedback from wrong answers | Unique (part of U1) |

### 2.7 Model Hub (R5)
| Feature | Tag |
|---|---|
| Provider keys once, used by both engines (about 10 providers) | Standard |
| Named model presets per capability | Standard |
| Latency- and cost-aware model routing | Unique (U8) |

### 2.8 Integration Hub (R5)
| Feature | Tag |
|---|---|
| MCP servers, REST and GraphQL tools, webhooks | Standard |
| Per-agent tool grants and rate limits | Unique (U6) |
| Bring your own agent over WebSocket | Unique (U7) |

### 2.9 Monitoring and analytics (R4 to R5)
| Feature | Tag |
|---|---|
| Live sessions, executions, logs | Standard |
| Analytics charts: calls and runs, tokens by model, reply-time histogram, call heatmap, outcomes, change against last week | Standard |
| Cross-engine trace waterfall | Unique |
| Failure clustering with proposed fixes | Unique (U1) |
| Cost per resolved call | Unique (U8) |

### 2.10 Organizations, members and security (R1, R6)
| Feature | Tag |
|---|---|
| Organizations, workspaces, 7 roles, invitations, Google and Microsoft sign-in | Standard |
| SAML SSO and SCIM provisioning | Standard (enterprise) |
| Masking of personal data by role | Unique (U6) |
| Hash-chained audit log | Unique (U6) |
| Data retention, export, deletion across engines | Standard |
| In-Kingdom and on-premises deployment | Unique with U9 |

### 2.11 Developer (R5)
| Feature | Tag |
|---|---|
| API keys, OAuth clients, rate limits, idempotency | Standard |
| Public API, Python and TypeScript SDKs, docs portal | Standard |
| Outgoing webhooks with delivery log and replay | Standard |

### 2.12 Billing and usage (R5 to R6)
| Feature | Tag |
|---|---|
| Separate usage meters, plan limits, quotas | Standard |
| Stripe metered subscriptions | Standard |
| Cost per outcome reports | Unique (U8) |

## 3. Open questions
| # | Question | Default until decided |
|---|---|---|
| F1 | Which Arabic STT/TTS providers to integrate first | Benchmark 3 on real Saudi call audio before choosing |
| F2 | WhatsApp channel provider | Meta Cloud API directly |
| F3 | Share of traffic for self-healing rollouts | 10 % for 24 hours, promote only on a measured win |
| F4 | Whether to market U9 at launch | Launch with U1, U2, U4, U6; U9 when the dialect benchmark is done |
