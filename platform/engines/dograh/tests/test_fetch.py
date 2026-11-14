"""T2: fetch.sh clones the pinned engines read only and applies our patches (AC-1, AC-2).

Local tests use throwaway git repositories as stand-ins for Dograh and Pipecat, through the
test-only overrides ``NEXORA_ENGINE_LOCK`` and ``NEXORA_PATCH_DIR``. The ``network`` test
clones the real pinned commits.
"""

import os
import subprocess
from pathlib import Path

import pytest

ENGINE_DIR = Path(__file__).resolve().parents[1]
FETCH = ENGINE_DIR / "fetch.sh"


def git(*args: str, cwd: Path) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True,
                          capture_output=True, text=True).stdout.strip()


def make_repo(path: Path, files: dict[str, str]) -> str:
    path.mkdir(parents=True)
    git("init", "-q", "-b", "main", cwd=path)
    git("config", "uploadpack.allowAnySHA1InWant", "true", cwd=path)
    for name, text in files.items():
        (path / name).parent.mkdir(parents=True, exist_ok=True)
        (path / name).write_text(text)
    git("add", ".", cwd=path)
    git("commit", "-q", "-m", "init", cwd=path)
    return git("rev-parse", "HEAD", cwd=path)


@pytest.fixture
def engines(tmp_path: Path):
    """Fake Dograh and Pipecat repos, a lock file pointing at them, and a patch dir."""
    pip_sha = make_repo(tmp_path / "pipecat-src", {"README": "pipecat\n"})
    dog_sha = make_repo(tmp_path / "dograh-src", {"api/factory.py": "ENGINES = {'rnnoise': 1}\n"})
    lock = tmp_path / "ENGINE.lock"
    lock.write_text(
        f"DOGRAH_REPO=file://{tmp_path / 'dograh-src'}\nDOGRAH_COMMIT={dog_sha}\n"
        f"PIPECAT_REPO=file://{tmp_path / 'pipecat-src'}\nPIPECAT_COMMIT={pip_sha}\n"
    )
    patches = tmp_path / "patches"
    patches.mkdir()
    return {"lock": lock, "patches": patches, "dograh": dog_sha, "pipecat": pip_sha, "tmp": tmp_path}


GOOD_PATCH = """--- a/api/factory.py
+++ b/api/factory.py
@@ -1 +1 @@
-ENGINES = {'rnnoise': 1}
+ENGINES = {'rnnoise': 1, 'nexora': 2}
"""

STALE_PATCH = """--- a/api/factory.py
+++ b/api/factory.py
@@ -1 +1 @@
-ENGINES = {'something_else': 1}
+ENGINES = {'something_else': 1, 'nexora': 2}
"""


def run_fetch(target: Path, env_extra: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(FETCH), str(target)], capture_output=True, text=True,
                          env={**os.environ, **env_extra})


def test_fetch_applies_patches_at_pinned_commits_local(engines):
    (engines["patches"] / "0001-good.patch").write_text(GOOD_PATCH)
    target = engines["tmp"] / "out"
    res = run_fetch(target, {"NEXORA_ENGINE_LOCK": str(engines["lock"]),
                             "NEXORA_PATCH_DIR": str(engines["patches"])})
    assert res.returncode == 0, res.stderr
    assert git("rev-parse", "HEAD", cwd=target) == engines["dograh"]
    assert git("rev-parse", "HEAD", cwd=target / "pipecat") == engines["pipecat"]
    assert "'nexora': 2" in (target / "api/factory.py").read_text()


def test_fetch_fails_loudly_on_drift(engines):
    (engines["patches"] / "0001-good.patch").write_text(GOOD_PATCH)
    (engines["patches"] / "0002-stale.patch").write_text(STALE_PATCH)
    target = engines["tmp"] / "out"
    res = run_fetch(target, {"NEXORA_ENGINE_LOCK": str(engines["lock"]),
                             "NEXORA_PATCH_DIR": str(engines["patches"])})
    assert res.returncode != 0
    assert "0002-stale.patch" in res.stderr
    # nothing applied: the good patch must not be half-applied either
    assert "'nexora'" not in (target / "api/factory.py").read_text()


def test_fetch_refuses_non_empty_target(engines, tmp_path):
    target = tmp_path / "busy"
    target.mkdir()
    (target / "something").write_text("x")
    res = run_fetch(target, {"NEXORA_ENGINE_LOCK": str(engines["lock"]),
                             "NEXORA_PATCH_DIR": str(engines["patches"])})
    assert res.returncode != 0
    assert "not empty" in res.stderr
    assert (target / "something").read_text() == "x"


def test_fetch_requires_target_argument():
    res = subprocess.run(["bash", str(FETCH)], capture_output=True, text=True)
    assert res.returncode != 0
    assert "usage" in res.stderr.lower()


@pytest.mark.network
def test_fetch_real_pins(tmp_path):
    target = tmp_path / "dograh"
    res = run_fetch(target, {})
    assert res.returncode == 0, res.stderr
    assert git("rev-parse", "HEAD", cwd=target) == "d672de2947da691fbc4542b62b914547a80e01ab"
    assert git("rev-parse", "HEAD", cwd=target / "pipecat") == "9ac08e90be4bb83e506f3d10deaa8e6d31588547"
    factory = (target / "api/services/pipecat/noise_reduction/factory.py").read_text()
    assert '"nexora": _nexora_filter' in factory
