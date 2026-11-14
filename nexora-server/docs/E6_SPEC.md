# E6: production infrastructure (spec)

Phase E6 of `ENTERPRISE_PLAN.md`, started 2026-11-14 on the user's instruction to build the
remaining phases in order ("build next E and so on"), logging problems in
`OPEN_ISSUES.md` rather than stopping.

Acceptance (from the plan): scales out and in under load without dropping sessions; limits
hold across instances.

## 1. Cluster-wide organization limits (Redis)

Today each instance counts an organization's open sessions itself, so with N instances an
organization can open N times its limit.

- `NEXORA_REDIS_URL` set: each session takes a **lease** in a Redis sorted set per
  organization (`nexora:org:<id>:leases`, member = lease id, score = expiry time from the
  Redis clock). A Lua script removes expired leases, checks the count against the limit and
  adds the new lease in one atomic step.
- Leases expire after `NEXORA_LEASE_TTL_S` (30 s) and are renewed every third of that while
  the session runs, so an instance that crashes frees its slots within 30 s.
- **Redis down**: the instance falls back to its own local count (it does not refuse calls),
  logs a warning and counts `nexora_limiter_errors_total`. Calls keep working; the limit is
  then per instance until Redis is back.
- Not set: the local count, as before (single instance, dev, tests).
- The per-instance capacity (`NEXORA_MAX_SESSIONS`) stays local: it protects that machine's CPU.

## 2. Draining: scale-in without dropping calls

- On the first SIGTERM the server **drains**: `/readyz` returns 503 with `draining: true` (so
  Kubernetes stops sending it traffic), new sessions get close code 1013 "server draining,
  retry another instance", and open sessions carry on.
- It exits once no sessions are left, or after `NEXORA_DRAIN_TIMEOUT_S` (default 600 s); a
  second SIGTERM exits at once. `nexora_draining` gauge is 1 while draining.
- Kubernetes: `terminationGracePeriodSeconds` = drain timeout + 60 s, and a 5 s `preStop` sleep
  so endpoint removal propagates before draining starts.

## 3. Database migrations (Alembic)

- Migrations ship inside the package (`nexora_server/migrations`); the first one is the
  current schema. `nexora-server migrate` runs `upgrade head`.
- `NEXORA_AUTO_MIGRATE` (default true) runs the upgrade at start-up, for single instances. In
  Kubernetes it is false and a `Job` runs `nexora-server migrate` before the rollout, so
  replicas never race.
- A database created by the old `create_all` (tables present, no `alembic_version`) is
  stamped as the first revision instead of being recreated.
- Test: after `upgrade head` the database matches the models exactly (Alembic
  `compare_metadata` finds no difference); downgrade to base and upgrade again works.

## 4. Kubernetes manifests (`deploy/k8s/`, Kustomize)

Namespace, ConfigMap, Secret template (no values), Deployment (probes, resources,
non-root, read-only root file system, drain settings), Service, Ingress (nginx WebSocket
timeouts), HorizontalPodAutoscaler on **active sessions per pod** (custom metric
`nexora_active_sessions` via prometheus-adapter, rule included) with CPU as a second
metric, PodDisruptionBudget (`maxUnavailable: 1`), migrations (an init container per pod since the bug round; a Job before),
and a single-node Redis for non-production use (production: a managed Redis).
Validated offline against the Kubernetes 1.30 schemas in tests.

## Tests

- Org limit across two app instances sharing one Redis (fakeredis): the second instance
  refuses the session over the limit; a released lease frees the slot; an expired lease
  (crashed instance) frees it after the TTL; Redis errors fall back to the local count.
- Draining: readiness 503, new session refused with 1013, an open session finishes
  normally; the server's exit waits for active sessions and has a timeout.
- Migrations as above; manifests parse and validate.

## Not covered here (logged in OPEN_ISSUES.md)

A real cluster scale-out/in test under load (E10), calls longer than the drain timeout
(cut at the end of the drain), Redis high availability.
