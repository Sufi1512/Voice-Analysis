# NEXORA Core

Identity, organizations, workspaces, roles, audit log and secrets for NEXORA (P1).
Spec: `../../docs/P1_SPEC.md`, tickets: `../../docs/P1_TICKETS.md`.

```bash
uv sync --all-groups
uv run pytest                      # needs PostgreSQL; set NEXORA_TEST_ADMIN_URL if not localhost
uv run ruff check . && uv run ty check src
uv run nexora-core                 # serves on :8080 (NEXORA_* settings, see settings.py)
```
