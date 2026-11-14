"""T3: the Dograh API environment built by setup.sh (AC-3, D1, D6).

Runs inside the patched Dograh checkout (copied to ``api/tests/nexora/`` by run-tests.sh).
"""

from importlib import metadata
from pathlib import Path

import api

DOGRAH_ROOT = Path(api.__file__).resolve().parents[1]


def test_pipecat_is_dograh_fork():
    import pipecat

    pipecat_file = Path(pipecat.__file__).resolve()
    assert DOGRAH_ROOT / "pipecat" in pipecat_file.parents, (
        f"pipecat imported from {pipecat_file}, not Dograh's fork in {DOGRAH_ROOT / 'pipecat'}"
    )


def _points_at_fork(dist: metadata.Distribution) -> bool:
    """True if this pipecat-ai record belongs to Dograh's checkout, not a PyPI download.

    An editable install leaves two records for the same source: the venv's dist-info
    (with ``direct_url.json`` naming the checkout) and setuptools' ``*.egg-info`` inside
    the checkout itself.
    """
    location = Path(str(dist._path)).resolve()  # noqa: SLF001 - stdlib has no public path
    fork = (DOGRAH_ROOT / "pipecat").resolve()
    if fork in location.parents:
        return True
    direct_url = dist.read_text("direct_url.json") or ""
    return fork.as_uri() in direct_url


def test_nexora_audio_installed_without_pipecat_extra():
    assert metadata.distribution("nexora-audio").version
    pipecat_dists = [d for d in metadata.distributions() if (d.metadata["Name"] or "").lower() == "pipecat-ai"]
    assert pipecat_dists, "pipecat-ai not installed"
    strays = [str(d._path) for d in pipecat_dists if not _points_at_fork(d)]  # noqa: SLF001
    assert not strays, f"Pipecat from outside Dograh's fork: {strays}"


def test_nexora_filter_importable_with_fork():
    from nexora_audio.integrations.pipecat import NexoraAudioFilter
    from pipecat.audio.filters.base_audio_filter import BaseAudioFilter

    assert issubclass(NexoraAudioFilter, BaseAudioFilter)
