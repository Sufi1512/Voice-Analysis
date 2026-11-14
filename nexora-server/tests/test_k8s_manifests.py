"""E6: the Kubernetes manifests in deploy/k8s parse, validate against the Kubernetes API
schemas (offline) and agree with the server's drain and migration settings."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

yaml = pytest.importorskip("yaml")
kv = pytest.importorskip("kubernetes_validate")

K8S = Path(__file__).resolve().parents[2] / "deploy" / "k8s"
NOT_OBJECTS = {"kustomization.yaml", "prometheus-adapter-rules.yaml"}


def objects() -> list[dict[str, Any]]:
    out = []
    for f in sorted(K8S.glob("*.yaml")):
        if f.name not in NOT_OBJECTS:
            out += [d for d in yaml.safe_load_all(f.read_text()) if d]
    return out


def by_kind(kind: str, name: str | None = None) -> dict[str, Any]:
    names = {"ConfigMap": "nexora-config"}
    want = name or names.get(kind, "nexora-server")
    return next(o for o in objects() if o["kind"] == kind and o["metadata"]["name"] == want)


@pytest.mark.parametrize("version", ["1.30.0", "1.33.0"])
def test_manifests_validate(version: str) -> None:
    objs = objects()
    assert len(objs) >= 10
    for o in objs:
        kv.validate(o, version, strict=True)  # raises on any schema error


def test_validator_catches_mistakes() -> None:
    bad = by_kind("Deployment")
    bad = {**bad, "spec": {**bad["spec"], "replicas": "two"}}
    with pytest.raises(Exception):  # noqa: B017 - any validation error
        kv.validate(bad, "1.30.0", strict=True)


def test_kustomization_lists_every_manifest() -> None:
    k = yaml.safe_load((K8S / "kustomization.yaml").read_text())
    listed = set(k["resources"])
    present = {f.name for f in K8S.glob("*.yaml")} - NOT_OBJECTS - {"secret.example.yaml"}
    assert listed == present
    assert "secret.example.yaml" not in listed  # never apply placeholder secrets


def test_drain_fits_in_the_grace_period() -> None:
    cfg = by_kind("ConfigMap")["data"]
    dep = by_kind("Deployment")
    spec = dep["spec"]["template"]["spec"]
    pre_stop, margin = 5, 30
    drain = float(cfg["NEXORA_DRAIN_TIMEOUT_S"])
    assert spec["terminationGracePeriodSeconds"] >= drain + pre_stop + margin
    assert dep["spec"]["strategy"]["rollingUpdate"]["maxUnavailable"] == 0
    assert cfg["NEXORA_AUTO_MIGRATE"] == "false"  # the Job migrates, not every replica


def test_hpa_targets_sessions_below_capacity() -> None:
    hpa = by_kind("HorizontalPodAutoscaler")
    cfg = by_kind("ConfigMap")["data"]
    assert hpa["spec"]["scaleTargetRef"]["name"] == by_kind("Deployment")["metadata"]["name"]
    pods = next(m for m in hpa["spec"]["metrics"] if m["type"] == "Pods")["pods"]
    assert pods["metric"]["name"] == "nexora_active_sessions"
    assert float(pods["target"]["averageValue"]) < int(cfg["NEXORA_MAX_SESSIONS"])


def test_containers_run_locked_down() -> None:
    for o in objects():
        if o["kind"] not in ("Deployment", "Job"):
            continue
        pod = o["spec"]["template"]["spec"]
        assert pod["securityContext"]["runAsNonRoot"] is True
        for c in pod["containers"]:
            sc = c["securityContext"]
            assert sc["readOnlyRootFilesystem"] and not sc["allowPrivilegeEscalation"]
            assert "limits" in c["resources"]


def test_trusting_all_proxies_needs_a_network_policy() -> None:
    """With X-Forwarded-For trusted from anywhere, only the ingress may reach the pods, or
    any pod in the cluster could fake its IP and dodge the per-IP connection limit."""
    cfg = by_kind("ConfigMap")["data"]
    if cfg.get("NEXORA_FORWARDED_ALLOW_IPS") != "*":
        return
    pol = by_kind("NetworkPolicy")
    labels = by_kind("Deployment")["spec"]["template"]["metadata"]["labels"]
    assert pol["spec"]["podSelector"]["matchLabels"].items() <= labels.items()
    assert pol["spec"]["policyTypes"] == ["Ingress"]
    sources = [s for rule in pol["spec"]["ingress"] for s in rule["from"]]
    assert sources and all("namespaceSelector" in s for s in sources)
