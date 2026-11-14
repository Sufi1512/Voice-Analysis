"""T7: the platform CI workflow (AC-8): Linux only, never pushes, runs the P0 chain."""

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[5]
WORKFLOW = REPO / ".github" / "workflows" / "platform.yml"


def load() -> dict:
    return yaml.safe_load(WORKFLOW.read_text())


def all_steps(doc: dict):
    for job in doc["jobs"].values():
        yield from job.get("steps", [])


def test_runs_on_platform_and_audio_changes():
    triggers = load()[True]  # PyYAML reads the bare key `on` as True
    for event in ("push", "pull_request"):
        paths = triggers[event]["paths"]
        assert "platform/**" in paths and "nexora-audio/**" in paths
        assert ".github/workflows/platform.yml" in paths


def test_workflow_has_no_push_or_macos():
    doc = load()
    for name, job in doc["jobs"].items():
        assert "ubuntu" in str(job["runs-on"]), f"{name} is not on Linux"
        assert "macos" not in str(job["runs-on"]).lower()
    text = WORKFLOW.read_text()
    for forbidden in ("git push", "docker push", "push: true", "gh release", "gh pr merge"):
        assert forbidden not in text, forbidden


def test_read_only_permissions():
    assert load()["permissions"] == {"contents": "read"}


def test_test_job_runs_the_p0_chain():
    steps = " ".join(s.get("run", "") for s in load()["jobs"]["dograh-tests"]["steps"])
    order = [steps.index(k) for k in ("--wheel", "fetch.sh", "setup.sh", "run-tests.sh")]
    assert order == sorted(order), "wheel -> fetch -> setup -> run-tests"
    assert "tests/host" in steps


def test_image_job_builds_patched_dograh_with_wheel():
    job = load()["jobs"]["dograh-image"]
    steps = " ".join(s.get("run", "") for s in job["steps"])
    assert "fetch.sh" in steps and "api/Dockerfile" in steps and "Dockerfile.nexora" in steps
    assert "docker run" in steps  # smoke check inside the built image
