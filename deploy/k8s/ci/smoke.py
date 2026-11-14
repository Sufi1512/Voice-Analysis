"""Real-cluster checks for the Kubernetes manifests (CI, on kind). OPEN_ISSUES I-017/I-020.

Run after ``kubectl apply -k deploy/k8s/ci`` and a finished rollout. Talks to the pods with
``kubectl port-forward`` and checks, on a real cluster:

1. the pods became ready with a read-only root file system, migrations ran in the init
   container, and a call works end to end;
2. the organization's concurrent-call limit holds across pods (Redis leases);
3. scale-in: a pod being shut down refuses new calls (1013) but lets its open call finish;
4. a pod killed outright: its call is closed as lost by another pod's sweeper, with the
   audio saved at the last checkpoint.

Needs: kubectl, Python with httpx, websockets, numpy.
"""

from __future__ import annotations

import asyncio
import json
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Self

import httpx
import numpy as np
import websockets

NS = "nexora"
ADMIN = {
    "Authorization": "Bearer ci-only-admin-key"
}  # dummy value from ci/kustomization
CHUNK = 320 * 2  # 20 ms of 16 kHz pcm16


def kubectl(*args: str, check: bool = True) -> str:
    out = subprocess.run(
        ["kubectl", "-n", NS, *args], capture_output=True, text=True, check=False
    )
    if check and out.returncode:
        raise RuntimeError(f"kubectl {' '.join(args)}: {out.stderr}")
    return out.stdout


def ready_pods() -> list[str]:
    data = json.loads(
        kubectl(
            "get", "pods", "-l", "app.kubernetes.io/name=nexora-server", "-o", "json"
        )
    )
    pods = []
    for p in data["items"]:
        if p["metadata"].get("deletionTimestamp"):
            continue
        conds = {c["type"]: c["status"] for c in p["status"].get("conditions", [])}
        if conds.get("Ready") == "True":
            pods.append(p["metadata"]["name"])
    return sorted(pods)


def wait_for(what: str, ok: Any, timeout: float = 120.0, every: float = 1.0) -> Any:
    deadline = time.time() + timeout
    while time.time() < deadline:
        v = ok()
        if v:
            return v
        time.sleep(every)
    raise AssertionError(f"timed out waiting for {what}")


@contextmanager
def forward(target: str) -> Iterator[str]:
    """``kubectl port-forward`` to a pod or service; yields its base URL."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen(
        [
            "kubectl",
            "-n",
            NS,
            "port-forward",
            target,
            f"{port}:8080" if target.startswith("pod/") else f"{port}:80",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    try:

        def up() -> bool:
            try:
                return httpx.get(f"{base}/healthz", timeout=2).status_code == 200
            except httpx.HTTPError:
                return False

        wait_for(f"port-forward to {target}", up, timeout=30, every=0.3)
        yield base
    finally:
        proc.terminate()
        proc.wait(5)


def audio(seconds: float) -> bytes:
    t = np.arange(int(seconds * 16000)) / 16000
    env = 0.5 + 0.5 * np.sin(2 * np.pi * 3 * t)  # syllable-like loudness
    x = 0.3 * env * np.sin(2 * np.pi * 220 * t) + 0.01 * np.random.default_rng(
        0
    ).standard_normal(t.size)
    return (np.clip(x, -1, 1) * 32767).astype("<i2").tobytes()


class Call:
    """One WebSocket call, sent in real time, with a reader collecting server messages."""

    def __init__(self, base: str, key: str) -> None:
        self.url = base.replace("http", "ws") + "/v1/stream"
        self.key = key
        self.msgs: list[dict[str, Any]] = []
        self.close_code: int | None = None
        self.sent_s = 0.0

    async def __aenter__(self) -> Self:
        self.ws = await websockets.connect(
            self.url, additional_headers={"Authorization": f"Bearer {self.key}"}
        )
        first = json.loads(await self.ws.recv())
        self.msgs.append(first)
        self.reader = asyncio.create_task(self._read())
        return self

    @property
    def started(self) -> dict[str, Any]:
        return self.msgs[0]

    async def _read(self) -> None:
        try:
            async for m in self.ws:
                if isinstance(m, str):
                    self.msgs.append(json.loads(m))
        except websockets.ConnectionClosed:
            pass
        self.close_code = self.ws.close_code

    async def send(self, seconds: float) -> None:
        data = audio(seconds)
        t0 = time.monotonic()
        for i in range(0, len(data), CHUNK):
            await self.ws.send(data[i : i + CHUNK])
            self.sent_s += CHUNK / 2 / 16000
            await asyncio.sleep(
                max(0.0, t0 + (i // CHUNK + 1) * 0.02 - time.monotonic())
            )

    async def end(self) -> dict[str, Any]:
        await self.ws.send(json.dumps({"type": "end"}))
        await asyncio.wait_for(self.reader, 30)
        return next(m for m in self.msgs if m["type"] == "session.ended")

    async def __aexit__(self, *exc: object) -> None:
        self.reader.cancel()
        await self.ws.close()


def new_org(base: str, **fields: Any) -> str:
    r = httpx.post(
        f"{base}/v1/orgs", json={"name": "ci", **fields}, headers=ADMIN, timeout=10
    )
    r.raise_for_status()
    return str(r.json()["api_key"])


def step(name: str) -> None:
    print(f"\n== {name}", flush=True)


async def main() -> None:
    pods = wait_for(
        "two ready server pods", lambda: (p := ready_pods()) and len(p) >= 2 and p
    )
    print("pods:", pods)

    step(
        "1. ready with a read-only root file system; migrations ran in the init container"
    )
    for pod in pods:
        dep = json.loads(kubectl("get", "pod", pod, "-o", "json"))
        assert (
            dep["spec"]["containers"][0]["securityContext"]["readOnlyRootFilesystem"]
            is True
        )
        init = dep["status"]["initContainerStatuses"][0]
        assert (
            init["name"] == "migrate" and init["state"]["terminated"]["exitCode"] == 0
        ), init
    with forward("svc/nexora-server") as base:
        key = new_org(base)
        async with Call(base, key) as call:
            assert call.started["type"] == "session.started", call.started
            await call.send(3.0)
            ended = await call.end()
        assert call.close_code == 1000 and ended["audio_seconds"] >= 2.9, ended
        print(
            "call ok:", ended["audio_seconds"], "s, backends", call.started["backends"]
        )

    step("2. the organization limit holds across pods (Redis leases)")
    a, b = pods[:2]
    with forward(f"pod/{a}") as pa, forward(f"pod/{b}") as pb:
        key = new_org(pa, max_concurrent_sessions=1)
        async with Call(pa, key) as first:
            assert first.started["type"] == "session.started"
            async with Call(pb, key) as second:
                assert (
                    second.started["type"] == "error" and second.started["code"] == 4429
                ), second.started
                await asyncio.wait_for(second.reader, 10)
                assert second.close_code == 4429
            await first.end()
        async with Call(pb, key) as again:  # the lease was released
            assert again.started["type"] == "session.started"
            await again.end()
        print(
            "second call on the other pod refused with 4429; allowed after the first ended"
        )

    step(
        "3. scale-in: a pod shutting down refuses new calls and lets its open call finish"
    )
    with forward(f"pod/{a}") as pa:
        key = new_org(pa)
        async with Call(pa, key) as call:
            await call.send(2.0)
            kubectl("delete", "pod", a, "--wait=false")
            wait_for(
                "readiness to report draining",
                lambda: httpx.get(f"{pa}/readyz", timeout=3).status_code == 503,
                30,
                0.5,
            )
            async with Call(pa, key) as refused:
                assert (
                    refused.started["type"] == "error"
                    and refused.started["code"] == 1013
                ), refused.started
            await call.send(5.0)  # the call carries on while the pod drains
            ended = await call.end()
        assert call.close_code == 1000 and ended["audio_seconds"] >= 6.9, ended
        print("draining pod finished its call:", ended["audio_seconds"], "s")
    wait_for(
        "the drained pod to exit",
        lambda: a not in kubectl("get", "pods", "-o", "name", check=False),
        120,
        2,
    )
    wait_for("a replacement pod", lambda: len(ready_pods()) >= 2, 300, 3)

    step(
        "4. a pod killed outright: its call is swept as lost and keeps its checkpointed audio"
    )
    victim, survivor = ready_pods()[:2]
    with forward(f"pod/{survivor}") as ps:
        key = new_org(ps)
        with forward(f"pod/{victim}") as pv:
            call = Call(pv, key)
            await call.__aenter__()
            sid = call.started["session_id"]
            await call.send(5.0)  # checkpoints every 2 s in CI
            kubectl("delete", "pod", victim, "--grace-period=0", "--force")
            call.reader.cancel()

        def swept() -> dict[str, Any] | None:
            r = httpx.get(
                f"{ps}/v1/sessions/{sid}",
                headers={"Authorization": f"Bearer {key}"},
                timeout=5,
            )
            rec = r.json()
            return rec if rec.get("status") == "failed" else None

        rec = wait_for("the sweeper to close the lost call", swept, 60, 1)
        assert rec["close_reason"].startswith("lost"), rec
        assert rec["audio_seconds"] >= 2.0, rec  # saved by a checkpoint before the kill
        print("lost call closed by another pod:", rec["audio_seconds"], "s billed")

    print("\nall real-cluster checks passed")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        print("\nreal-cluster check FAILED", file=sys.stderr)
        raise
