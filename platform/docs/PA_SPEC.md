# PA: NEXORA AI portal, all screens on sample data

Status: **Draft, awaiting approval** · Date: 2026-11-14 · Owner: Sufi1512

## Problem and goal
The portal has sign-in, organizations and the audit log (P1 W1-W3) but none of the AI product.
Goal: every AI screen of NEXORA, built in the Signal Room design and working in the browser on
realistic sample data, so the whole product can be seen, demonstrated to Saudi enterprise
customers and reviewed before the engines are connected. Each screen is then switched to real
data in its engine phase (P2 Dograh, P3 Dify/graphon, P4, PK, P5, PU) without redesign.

Success: a 15-minute demo walks through building a voice agent, linking it to an AI workflow and
a knowledge base, watching a live call, opening its trace and acting on a failure insight, with no
dead ends, in dark and light, on desktop and phone.

## Decisions (grilling, 2026-11-14)
| Decision | Reason |
|---|---|
| All AI screens first on sample data; engines connected screen by screen later | User's choice: see and demo the whole portal first |
| Scope: AI Studio, Observability, Knowledge, Integrations and Developer | User's choice; Administration (members, workspaces, security) and the rest of P1 come after |
| Signal Room canvas "fully alive": React Flow builders, live signal lanes, animated traces, full chart set, dark and light | User's choice |
| Main unique features included: misheard-or-misunderstood, audio quality scores, answer budget, mid-call approvals, supervisor listen/whisper/take over, failure insights with proposed fixes | User's choice (U2.1, U2.2, U4.1, U6.1, U5.1, U1.1, U1.2) |
| Sample data: realistic Saudi enterprises (insurance, bank, hospital), Arabic and English callers, a "Sample data" badge that can be hidden for demos | User's choice |

## Scope
### In scope (navigation follows the product plan, section 11)
**Dashboard**: readouts (calls today, resolved without a person, median answer time, AI runs,
approvals waiting, average audio quality), live calls strip, call volume by hour (voice vs AI),
outcomes, recent failure clusters.

**AI Studio**
- *Voice agents*: list (status, language, calls today, resolution, quality); agent page with tabs
  Overview, Flow, Settings, Connections, Versions, Calls.
  - **Voice flow builder** (React Flow) using Dograh's node types exactly as in the pinned code
    (`api/services/workflow/dto.py` `NodeType`): start call, agent, global, trigger, webhook, QA,
    end call. Drag from a palette, connect, edit node properties in a side panel, validate
    (one start, every path ends), undo/redo, minimap, keyboard shortcuts.
  - Settings: prompt, voice, speech-to-text / text-to-speech / model choice, language
    (Arabic, English, both), noise reduction (nexora-audio) on/off.
  - Connections: tools that run an AI workflow or search a knowledge base during a call, with
    input mapping, the line said while waiting, and the answer budget.
  - **Test call**: a simulated call in the browser with live transcript, signal lane and the
    tools it calls (real WebRTC arrives in P2.7).
- *AI agents*: list; agent page with instructions, model, tools, knowledge; **preview chat**
  with streamed replies and visible tool calls.
- *Workflows*: list and **AI workflow builder** (React Flow, separate editor, same look):
  start, model, knowledge search, agent, approval, condition, HTTP request, code, template, end.
  Run panel with sample inputs; the running path animates node by node with inputs and outputs.
  Node set is NEXORA's plan (Architecture §3.1); graphon's built-in node names are **VERIFY**
  against graphon 0.8.0 before P3.
- *Applications*: published chat apps and endpoints with their channel and version.

**Knowledge**: knowledge bases; documents with a processing pipeline (uploaded, parsing,
chunking, embedding, ready, failed) and a **chunk preview** (page beside its chunks, tables shown
as tables, section path, why a passage matched); data sources (upload, website, connectors);
**search test** with scores and citations (Integration §11).

**Integrations**: model providers with per-engine status; MCP servers and their tools with
grants per agent; APIs (HTTP tools); webhooks with a delivery log and replay.

**Developer**: API keys (shown once, scoped, revoke); quickstart and SDK snippets (Python,
TypeScript, curl); API reference page.

**Observability**
- *Live sessions*: every active call as a signal lane (caller, agent, AI work, silence);
  **supervisor** listen, whisper, take over, hand back (simulated).
- *Executions*: list with filters; **trace** of one call: voice and AI steps on one timeline,
  **answer-budget line** and holding-line marker, transcript beside it, and the
  **misheard or misunderstood** panel (audio score, speech-to-text confidence, retrieval score,
  model step) naming the likely cause.
- *Logs*: searchable event log.
- *Analytics*: volume, resolution, answer time percentiles, transfer reasons, audio quality
  distribution, model latency, knowledge hit rate; time range filter; every chart has a table view.

**Unique features (sample data)**
- *Approvals inbox*: a call waiting on a payment-style action; approve or reject while the caller
  hears the holding line; result shown in the trace.
- *Insights*: failure clusters with counts and example calls, a **proposed fix** as a reviewable
  diff of the flow or prompt, a test set from real calls, and a rollout card (10 % for 24 h).
- *Audio quality*: score per call and per agent (noise, echo, background talkers, packet loss).

**Shell**: workspace switcher (sample workspaces until C9), global search (Cmd/Ctrl+K) across
agents, workflows, knowledge bases and calls, "Sample data" badge with a hide switch.

### Out of scope
- Any engine call: Dograh, Dify, graphon, the AI runtime (P2, P3).
- Real phone numbers, WebRTC, real model calls; saved changes persist only in the browser
  session (builders, settings) and reset on reload unless "Reset sample data" is used.
- Administration screens, MFA, password reset, Microsoft sign-in (rest of P1).
- Channels (web chat, WhatsApp), bring-your-own-agent, cost routing, Arabic dialect routing
  (other unique features, later).
- The Arabic translation itself (screens stay right-to-left ready as in P1).

## Users and permissions
Screens follow the P1 roles: Viewers see everything read-only; Developers build; Operators work
live sessions and approvals; Organization owners and admins do everything. On sample data the
role decides which buttons are enabled, so demos show the real permission model.

## Behaviour
### Main demo flow
1. Dashboard: three live calls, one approval waiting, a failure cluster flagged.
2. Voice agent "Insurance support line": open the flow, add an agent node, connect it, validate.
3. Connections: link the tool `check_policy` to the workflow "Policy lookup" with a 3.5 s budget.
4. Workflow "Policy lookup": run it with a sample policy number; the path animates.
5. Knowledge base "Motor policy terms": open a PDF's chunk preview; run a search test in Arabic.
6. Test call: the simulated caller asks about coverage; the tool runs; the agent answers.
7. Live sessions: listen to a call, take over, hand back.
8. Executions: open a failed call; the trace shows "misheard: audio quality 41/100".
9. Insights: open the cluster, review the proposed fix, start the 10 % rollout.

### Edge cases and empty states
Every list has an empty state that says what to create; every builder blocks publishing an
invalid graph and points at the problem node; long Arabic and English names wrap; failed
documents and executions show the reason and a retry; reduced motion freezes every lane and edge.

## Data
Sample data lives in the portal (typed fixtures), no database writes. Every screen reads through
a typed data source with two implementations: `sample` (now) and `core` (wired per screen in the
engine phases). Fixture content is invented; no real customer, phone number or recording.

## Interfaces
Routes under `/o/[org]/w/[ws]/...`: `dashboard`, `voice-agents`, `voice-agents/[id]/{flow,settings,
connections,versions,calls}`, `ai-agents`, `workflows`, `workflows/[id]`, `applications`,
`knowledge`, `knowledge/[id]`, `knowledge/[id]/documents/[doc]`, `integrations/{models,mcp,apis,
webhooks}`, `developer/{keys,quickstart,reference}`, `live`, `executions`, `executions/[id]`,
`logs`, `analytics`, `approvals`, `insights`. The data-source interfaces become the contract the
Core endpoints implement in P2-P5.

## Non-functional requirements
- Signal Room tokens and rules (ruled not carded, one action colour, amber = voice, lilac = AI,
  meaning never by colour alone); contrast test extended to chart colours.
- Builders stay smooth with 150 nodes; lists with 1,000 rows virtualised; first load of a screen
  under 2 s on the local stack; heavy parts (builders, charts) loaded only on their pages.
- Keyboard: builders fully usable without a mouse (add, connect, move, delete nodes).
- Right-to-left ready, every string translated (P1 lint rules apply); phone width works for
  every screen except the two builders, which show a read-only view on phones.
- Libraries: React Flow (`@xyflow/react`, MIT), Recharts (MIT), TanStack Query, Zustand for builder
  state (Architecture §10); each checked by the supply-chain audit before adding.

## Acceptance criteria
- [ ] PA-1 Every route above renders with sample data in dark and light, desktop and phone, with
      no console errors (Playwright visits every route).
- [ ] PA-2 The demo flow (Behaviour 1-9) runs end to end in Playwright.
- [ ] PA-3 Voice flow builder: create, connect, delete, undo/redo, validate; only Dograh's seven
      node types are offered; the saved graph matches Dograh's workflow definition shape
      (unit test against the pinned `dto.py` field names).
- [ ] PA-4 AI workflow builder: build and run a branching workflow; the run animates the taken path
      and shows each node's inputs and outputs.
- [ ] PA-5 Trace shows voice and AI steps on one timeline with the answer-budget line, and the
      misheard/misunderstood panel names the cause for both sample failure types.
- [ ] PA-6 Approvals, supervisor take-over and the insights rollout work on sample data and their
      effects show in the trace and audit view.
- [ ] PA-7 Charts: every chart has a table view and passes the colour validator in both themes.
- [ ] PA-8 RTL and translation lint pass; `dir="rtl"` renders every screen without overlap
      (screenshot check); Arabic transcript lines display right-to-left inside English screens.
- [ ] PA-9 Every screen reads through the data-source interface (a test fails if a page imports a
      fixture directly), so switching to Core is per screen.
- [ ] PA-10 The "Sample data" badge is on every sample screen and can be hidden for demos.

## Open questions
- None blocking. graphon's built-in node names are confirmed in P3; until then the AI workflow
  builder uses NEXORA's planned node set.
