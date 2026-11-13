# Module 1 — Public website & product discovery

**Status:** IN_PROGRESS (first pass from secondary + official sources)
**Last updated:** 2026-11-13

## 1. Scope and method
First-pass product inventory built from Krisp's own press releases, release
notes, blog and npm packages, plus dated third-party captures of krisp.ai.
krisp.ai pages were **not yet loaded directly**, so page structure, nav,
CTAs and screenshots are still outstanding (see §7).

## 2. Product families
| Family | Audience | Delivery | Evidence | Confidence |
|---|---|---|---|---|
| AI Meeting Assistant (Meeting AI) | Individuals, teams | Desktop app acting as virtual mic/speaker; web app for notes | E002, E004 | INFERRED |
| Call Center AI | Contact centers / BPOs | Desktop app + Krisp Widget + Admin Portal | E012, E015, E017 | VERIFIED |
| Developer platform | Builders of voice agents / RTC apps | VIVA SDK, RTC SDK, Translation API | E001, E021 | VERIFIED |

## 3. Feature inventory
| Feature | Family | Role | Entry point | Observable output | Evidence | Confidence |
|---|---|---|---|---|---|---|
| Noise cancellation (bidirectional) | Meeting, CC | User/agent | Desktop app, virtual devices | Cleaned mic + speaker audio | E004, E012 | VERIFIED (CC) / INFERRED (Meeting) |
| Background voice cancellation / voice isolation | Meeting, CC, Dev | User/agent | Desktop app; VIVA SDK | Other voices removed | E021, E025 | VERIFIED |
| Echo cancellation | Meeting | User | Desktop app | Reduced echo | S15 (2023 homepage) | INFERRED |
| Bot-free recording & transcription | Meeting | User | Desktop app / calendar | Transcript with speaker IDs + timestamps | E003 | INFERRED |
| Bot-based meeting join | Meeting | User | Calendar / meeting link | Transcript | E003 | HYPOTHESIS |
| AI notes, summaries, action items | Meeting | User | Meeting page | Notes, tasks | E005 | INFERRED |
| AI chat over meetings | Meeting | User | Meeting page | Answers | E005 | INFERRED |
| Custom vocabulary (≤750 terms) | Meeting | User | Settings | Better transcripts | E007 | INFERRED |
| Multilingual transcription (16–17+ languages) | Meeting | User | Settings | Non-English transcripts | S05 | INFERRED |
| Sharing (email), calendar auto-record, templates, CRM sync | Meeting | User | Meeting page / integrations | Shared notes | E005, S02 | INFERRED |
| Accent conversion (daily caps by plan) | Meeting, CC, Dev | User/agent | Desktop app; AC SDK | Converted accent | E009, E034 | VERIFIED |
| Live Interpreter / Voice Translation | CC, Dev | Agent | Desktop app; VT SDK/API | Translated speech | E012, E033 | VERIFIED |
| Agent Assist — Knowledge Chat | CC | Agent | Krisp Widget | Contextual answers from KB | E013 | VERIFIED |
| After-call summary + follow-ups + dispositions | CC | Agent | Krisp Widget | Summary, category | E013, E016 | VERIFIED |
| PII/PCI redaction before LLM | CC | System | — | Masked AI input | E014 | VERIFIED |
| Instant call score (0–100) | CC | Agent | Krisp Widget | Score | E015 | VERIFIED |
| Speech analytics, Smart Captions | CC | Supervisor/agent | Widget / portal | Analytics, captions | E018 | VERIFIED (exists), detail UNKNOWN |
| Admin Portal (team settings → features) | CC, Meeting | Admin | Admin Portal | Feature toggles | E015 | VERIFIED |
| Usage analytics, real-time monitoring | CC | Admin | Admin Portal | Dashboards | S06 | INFERRED |
| SSO/SCIM, super-admin, HIPAA/BAA | Enterprise | Admin | Admin Portal | — | E010 | INFERRED |
| Local monitoring WebSocket (localhost) | Integrations | Developer | Krisp Desktop | Device + NC/AC + in-call state | E020 | VERIFIED |

## 4. Plans (as captured by dated third-party checks)
| Plan | Price | Key limits | Evidence |
|---|---|---|---|
| Meeting AI trial | 7 days, no card | All premium features | E008 |
| Core | $8/user/mo annual · $16 monthly | 10 GB storage; AC 1 h/day | E008, E009 |
| Advanced | $15 annual · $30 monthly | 60 GB; AC 4 h/day (speaker) | E008, E009 |
| Enterprise | Contact sales | SSO/SCIM, on-device transcription, HIPAA, BAA ≥100 seats | E010 |
| CC Core | **Conflict:** $10 vs $15/agent/mo | Agent+customer NC, voice isolation, monitoring | E011 |
| CC Advanced | Contact sales, 14-day eval | Accent conversion, Knowledge Chat, captions | E011 |
| Developer Early Stage / Enterprise | Contact sales | — | S06 |

## 5. Shared platform services (inferred)
Identity/SSO, Admin Portal with team-level feature flags, desktop audio
engine (virtual devices), widget UI, usage analytics, LLM summarisation with a
redaction step, knowledge base, billing/plan limits (daily minute caps).

## 6. Duplicate capabilities across families
Noise cancellation, voice isolation, accent conversion and translation appear
in Meeting AI, Call Center AI *and* as SDKs, which suggests one shared audio
model layer packaged three ways (INFERRED).

## 7. Outstanding (needs direct krisp.ai capture)
- Page inventory: nav, dropdowns, every section, CTA destinations, forms.
- Full-page + responsive screenshots.
- Resolve CC Core price conflict.
- Confirm certifications on the official trust page.
