# NEXORA AI

**One Platform. Infinite Intelligence.**

This folder holds the NEXORA platform code inside the Voice-Analysis repo.

NEXORA is an enterprise AI platform that combines real-time voice agents (Dograh),
AI workflows and agents (graphon / Dify), shared knowledge, model management and
governance behind one portal and one API.

## Status
Phase P0 (foundations) of the [implementation roadmap](docs/NEXORA_IMPLEMENTATION_ROADMAP.md).

## Layout (target)
```
apps/web            NEXORA Portal (Next.js)
apps/docs           Developer portal
services/core       nexora-core (identity, tenancy, RBAC, registry, orchestrator, ...)
services/ai-runtime graphon-based AI runtime
packages/           Shared UI, API client, config
sdks/               Python and TypeScript SDKs
engines/            Pinned engine versions and overlays
infrastructure/     Docker, Kubernetes/Helm, monitoring
docs/               Architecture, database, integration spec, roadmap, engine audits
(skills)            Project skills live at the repo root in /.claude/skills (see /.claude/SKILLS.md)
```

## Docs
- [Product plan](docs/NEXORA_PRODUCT_PLAN.md)
- [Feature catalogue](docs/NEXORA_FEATURES.md)
- [Design canvas: Signal Room](https://claude.ai/artifact/9w5bzWzzctRNkfz7b7ESzD)
- [System architecture](docs/NEXORA_SYSTEM_ARCHITECTURE.md)
- [Database architecture](docs/NEXORA_DATABASE_ARCHITECTURE.md)
- [Integration specification](docs/NEXORA_INTEGRATION_SPECIFICATION.md)
- [Implementation roadmap](docs/NEXORA_IMPLEMENTATION_ROADMAP.md)
