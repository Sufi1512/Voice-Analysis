# Kubernetes deployment (E6)

```sh
kubectl create namespace nexora
kubectl -n nexora create secret generic nexora-secrets \
  --from-literal=NEXORA_SECRET_KEY="$(openssl rand -base64 48)" \
  --from-literal=NEXORA_ADMIN_API_KEY="$(openssl rand -base64 32)" \
  --from-literal=NEXORA_DATABASE_URL="postgresql+psycopg://USER:PASSWORD@HOST:5432/nexora"
cd deploy/k8s && kustomize edit set image nexora-server=<registry>/nexora-server:<tag>
kubectl apply -k .
helm install prometheus-adapter prometheus-community/prometheus-adapter \
  -f prometheus-adapter-rules.yaml   # for the sessions-per-pod autoscaling
```

| Piece | What it does |
| --- | --- |
| Migrations | Each pod's init container runs `nexora-server migrate` (Alembic) first; pods starting together wait on a PostgreSQL advisory lock, so a new image needs no extra step. Migrations must stay compatible with the release still running during a rollout. |
| `deployment.yaml` | 2+ pods, 4 CPUs each (8 sessions per pod, measured in E10), non-root, read-only file system. Rolling updates never reduce capacity (`maxUnavailable: 0`) |
| Draining | SIGTERM: `/readyz` turns 503, new calls get close code 1013 (clients retry and land on another pod), open calls carry on for up to 600 s; grace period 660 s |
| `hpa.yaml` | Scales on open calls per pod (target 5 of 8) and CPU; scale-in removes one pod per 2 minutes |
| `pdb.yaml` | At most one pod voluntarily down at a time |
| `redis.yaml` | Leases for organization limits across pods. Single node, for testing; use a managed Redis in production |
| `ingress.yaml` | ingress-nginx with 1-hour WebSocket timeouts and a per-IP request limit; set your host and TLS secret |
| `networkpolicy.yaml` | Only the ingress controller and Prometheus namespaces reach the server pods (keeps the forwarded client IP trustworthy for per-IP limits) |

Clients must reconnect on close code 1013 (see `nexora-client`). Calls longer than the
drain timeout are cut when the pod stops.
