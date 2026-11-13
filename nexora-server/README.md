# Nexora Voice Cloud (nexora-server)

Enterprise real-time voice processing for AI agents. Customers stream audio over
WebSocket. Nexora removes noise, cleans pauses, enhances the voice, and reports when the
user starts, stops, finishes a turn or interrupts. Multi-tenant, metered and observable.
Run it as SaaS or inside a customer's VPC.

Architecture, data model, security model and roadmap: [`docs/ENTERPRISE_PLAN.md`](docs/ENTERPRISE_PLAN.md).

## Run it

```bash
# Docker (PostgreSQL + server + Prometheus), from the repository root
cp deploy/.env.example deploy/.env        # set the secrets
docker compose -f deploy/docker-compose.yml --env-file deploy/.env up --build

# Or directly (SQLite, dev only)
pip install -e ../nexora-audio -e .
NEXORA_SECRET_KEY=dev-secret NEXORA_ADMIN_API_KEY=dev-admin nexora-server --port 8080
```

Interactive API docs: `http://localhost:8080/docs`.

| Setting (env) | Default | Meaning |
|---|---|---|
| `NEXORA_DATABASE_URL` | `sqlite:///./nexora.db` | Use `postgresql+psycopg://…` in production |
| `NEXORA_SECRET_KEY` | random (warns) | Signs session tokens, peppers API-key hashes. **Same value on every instance** |
| `NEXORA_ADMIN_API_KEY` | none | Super-admin key, only for creating organizations |
| `NEXORA_DEPLOYMENT_MODE` | `saas` | `saas`: relay targets must be `wss://` public hosts. `self_hosted`: allowlist only |
| `NEXORA_MAX_SESSIONS` | 4 × CPU cores | Instance capacity. Beyond it, connections close with 1013 |
| `NEXORA_WORKER_THREADS` | CPU cores | Audio processing threads |
| `NEXORA_IDLE_TIMEOUT_S` | 30 | Close sessions that send nothing (code 4408) |
| `NEXORA_MAX_MESSAGE_BYTES` | 262144 | Larger audio messages close with 1009 |
| `NEXORA_SESSION_TOKEN_TTL_S` | 300 | Default session-token lifetime |
| `NEXORA_CORS_ORIGINS` | none | Comma-separated origins for browser REST calls |

## Onboard a customer

```bash
# 1. You (super-admin) create the organization -> returns its first admin API key (shown once)
curl -X POST $NEXORA/v1/orgs -H "Authorization: Bearer $ADMIN_KEY" \
  -H 'content-type: application/json' \
  -d '{"name": "Acme", "max_concurrent_sessions": 50, "monthly_minutes_quota": 100000,
       "relay_allowlist": ["agent.acme.com"]}'

# 2. The customer creates keys and profiles with their admin key
curl -X POST $NEXORA/v1/keys -H "Authorization: Bearer $ACME_ADMIN" \
  -d '{"name": "voice-gateway", "scopes": ["stream"]}' -H 'content-type: application/json'
curl -X POST $NEXORA/v1/profiles -H "Authorization: Bearer $ACME_ADMIN" -H 'content-type: application/json' \
  -d '{"name": "phone", "is_default": true,
       "audio_settings": {"clarity_db": 4},
       "turn_settings": {"end_of_turn_ms": 800, "interruption_min_ms": 350}}'
```

Scopes: `stream` (use the audio endpoints, mint session tokens), `admin` (keys, profiles,
audit), `usage:read` (sessions, usage).

## Stream audio

### Process mode: `wss://HOST/v1/stream`
Your system sends audio and receives cleaned audio plus events on the same socket.

```
wss://HOST/v1/stream?encoding=pcm16&sample_rate=16000&profile=phone
Authorization: Bearer nx_…            (server-side)   or   ?token=<session token>  (browser/mobile)
```

### Relay mode: `wss://HOST/v1/relay?target=wss://agent.acme.com/ws`
Your caller connects to Nexora. Nexora connects to your agent (allowlisted host only),
sends it cleaned audio plus events, and forwards agent audio and messages back to the
caller. Interruptions are also sent straight to the caller so playback can stop at once.

### Query parameters
`encoding` (`pcm16` | `float32` | `mulaw` | `alaw`), `sample_rate` (8000–48000),
`channels` (1|2), `output_encoding`, `output_sample_rate`, `profile`, `target` (relay), `token`.

### Messages

| Direction | Message |
|---|---|
| client → server | binary audio, any chunk size (20 ms recommended) |
| client → server | `{"type":"agent_speaking","value":true}` (Process mode: your TTS is playing) |
| client → server | `{"type":"flush"}`, `{"type":"reset"}`, `{"type":"end"}`, `{"type":"ping"}` |
| server → client | binary cleaned audio in the output format |
| server → client | `{"type":"session.started","session_id":…,"backends":…,"latency_ms":…}` |
| server → client | `{"type":"speech_start"\|"speech_end"\|"end_of_turn"\|"interruption"\|"backchannel","time_ms":…}` |
| server → client | `{"type":"session.ended","audio_seconds":…,"events":{…},"close_code":…}` |
| server → client | `{"type":"error","code":…,"message":…}` (followed by close with that code) |

### Close codes

| Code | Meaning | What to do |
|---|---|---|
| 1000 | Normal end | — |
| 1009 | Message too big | Send smaller chunks |
| 1011 | Internal error | Retry; report the session ID |
| 1013 | Instance at capacity | Retry (the load balancer picks another instance) |
| 4001 | Missing/invalid API key or token | Check credentials or mint a new token |
| 4003 | Forbidden (scope, inactive org, relay target not allowed) | Fix permissions or the allowlist |
| 4004 | Profile not found | Check the profile name |
| 4400 | Bad request (audio format, missing relay target) | Fix the parameters |
| 4402 | Monthly audio quota exhausted | Raise the quota |
| 4408 | Idle timeout | Send audio or keep-alive pings |
| 4429 | Organization concurrency limit reached | Raise `max_concurrent_sessions` or wait |
| 4502 | Relay could not reach the agent | Check the agent URL and that it is up |

### Python client

```python
from nexora_client import NexoraClient

async with NexoraClient("https://voice.example.com", api_key="nx_…") as nx:
    async with nx.stream(encoding="mulaw", sample_rate=8000, profile="phone") as stream:
        await stream.send_audio(chunk)
        async for msg in stream:
            if msg.audio:
                ...                      # cleaned audio -> your STT / agent
            elif msg.type == "end_of_turn":
                ...                      # user finished: run the LLM
            elif msg.type == "interruption":
                ...                      # stop TTS
```

## Operate it

- `GET /healthz`: liveness. `GET /readyz`: readiness (DB reachable, models loaded, capacity left).
- `GET /metrics`: Prometheus. `nexora_active_sessions`, `nexora_capacity_sessions`,
  `nexora_sessions_total{mode,outcome}`, `nexora_rejections_total{reason}`,
  `nexora_audio_seconds_total`, `nexora_turn_events_total`,
  `nexora_chunk_processing_seconds`, `nexora_session_start_seconds`.
- Logs: one JSON line per event, with `session_id` and `org_id`. Audio and keys are never logged.
- Usage and billing: `GET /v1/usage` (audio minutes per day, month to date, quota);
  every session is recorded in `/v1/sessions`.
- Capacity: about 4 concurrent calls per CPU core with the default pipeline
  (`nexora-audio/docs/benchmarks.md`). Scale out by adding instances behind a
  WebSocket-capable load balancer. The secret key and database are shared; nothing else is.
- Warm pool: each instance pre-loads models and keeps recently used session types ready,
  so a new call starts in milliseconds instead of ~0.5 s.

## Security
- API keys are 256-bit, shown once, stored as HMAC-SHA256 with a server pepper. Revocable.
- Browsers and mobile apps get 5-minute session tokens minted by the customer's backend.
- No audio is stored, only session metadata (duration, event counts, timings).
- Relay only to allowlisted hosts. In SaaS mode also `wss://` only, with private,
  loopback, link-local and metadata addresses blocked. Re-checked at connect time.
- Every admin action is in the audit log (`GET /v1/audit`).
- Runs as a non-root user in the container. TLS terminates at your load balancer.

## Known limits (E1)
- Concurrency limits are per instance (per-org counts are not shared across instances yet: E2 adds Redis).
- Tables are created at startup. Alembic migrations come in E2.
- Tested on SQLite. PostgreSQL is supported through SQLAlchemy but not exercised in CI here.
- Turn and interruption detection is rule-based (see nexora-audio README).
