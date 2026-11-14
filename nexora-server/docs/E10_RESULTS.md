# E10: load, soak, chaos and security (results)

Phase E10 of `ENTERPRISE_PLAN.md`, run 2026-11-14 on the user's instruction to build the
remaining phases in order. Acceptance in the plan: agreed targets hold for 72 hours with
hundreds of concurrent sessions; no open high-severity findings. **What fits on this machine
was run; the 72-hour, hundreds-of-sessions run needs real infrastructure (I-037).**

Machine: 2 shared vCPUs (x86_64), one server process (`nexora-server`, SQLite), the load
generator on the same machine. Load tool: `nexora-server/loadtest` (`python -m loadtest`):
N callers stream 20 ms PCM16 chunks in real time (speech with pauses) and read the cleaned
audio back; round trip = sending a chunk to receiving the output that completes it.

## Capacity: the default was too high

| Concurrent calls | Calls ok / failed | Round trip p50 / p95 / p99 / max |
| --- | --- | --- |
| 1 | 1 / 0 | 7 / 10 / 53 / 71 ms |
| 2 | 4 / 0 | 8 / 13 / 67 / 318 ms |
| 3 | 5 / 0 | 7 / 24 / 328 / 499 ms |
| 4 (new default for 2 CPUs) | 7 / 0 | 10 / 41 / 170 / 417 ms |
| 8 (old default: 4 per core) | 3 / **5 timed out** | **12,086** / 22,114 / 22,812 ms |

The old default (4 calls per core, measured before E2-E5 added the speech guard, echo gate,
background-talker gate and Smart Turn) collapses: the work queue grows and every call falls
seconds behind. Changes:

- Default capacity **2 calls per CPU core** (`NEXORA_MAX_SESSIONS`); Kubernetes: 8 per 4-CPU
  pod, autoscaling target 5.
- **Overload guard**: if audio jobs queue up beyond 2 x worker threads, new calls are refused
  with 1013 and `/readyz` turns red, instead of every call slowing down
  (`nexora_work_queue_depth`, rejection reason `overloaded`).
- Part of the limit is Python's global interpreter lock: one process cannot spread all the
  per-chunk Python work over many cores. Measured only on 2 cores (I-038).

## Over capacity: refusals must be cheap

8 callers against capacity 4:

| Version | Admitted calls round trip p50 / p99 | Refusals |
| --- | --- | --- |
| Refusal after authentication, tester retrying without backoff | **12,717 / 17,538 ms** | 7,485 in 40 s |
| Refusal **before** authentication, tester backing off like `nexora_client` | **7.9 / 111 ms** | 56 |

A flood of refused connections was starving the admitted calls (each refusal cost a
database lookup and key check). Full, overloaded and draining instances now refuse first.
Edge rate limiting is still needed for hostile floods (I-035).

## Soak: 10 minutes, callers hanging up and redialling every 60 s

3 concurrent callers, 31 calls: **0 failed**, round trip p50 7.7 ms, p95 62 ms, p99 251 ms,
max 1.05 s (the slowest moments coincided with test suites running on the same 2 CPUs).
Server memory: 483 MB at start, 557 MB after 3 minutes (warm-up: models, pools, allocator),
then 557 to 564 MB over the last 7 minutes. Too short to rule out a slow leak (I-039).

## Chaos tests (`tests/test_chaos.py`, in CI)

| Failure | Behaviour |
| --- | --- |
| Caller vanishes mid-call (no close frame; also tested with a real TCP abort) | Slot freed, session recorded as ended **with the audio received before the drop**, next caller served |
| Database fails as the call ends | Caller still gets `session.ended`; slot freed; failure logged and counted (`nexora_session_record_errors_total`) |
| Audio engine raises mid-call | Caller gets 1011; session recorded `failed`; the broken session is not reused |
| Garbage input (odd-length audio, invalid/huge JSON, unknown types) | Errors returned; no crash; next caller served |
| Relay agent dies mid-call | Caller's session ends with the agent's reason; slot freed |

Two real bugs found and fixed: a caller who vanished left the session `active` forever (never
billed, audio session leaked), because sending the goodbye to a closed socket raised and the
task was cancelled; and a database error at the end of a call escaped and skipped the same
cleanup. End-of-call cleanup is now step by step and shielded from cancellation.

## Security review

`docs/SECURITY_REVIEW.md`: no known-vulnerable dependencies (96 packages), no high-severity
static-analysis findings; fixed a relay DNS-rebinding window, oversized WebSocket frames,
logout CSRF, asserts in security checks, missing no-store/nosniff headers. No open
high-severity findings from this review; it was not an independent penetration test (I-036).
