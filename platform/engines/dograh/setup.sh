#!/usr/bin/env bash
# Build a Python 3.13 environment for the patched Dograh API, the way Dograh's own
# scripts/setup_requirements.sh does, plus the nexora-audio wheel.
#
# Usage: setup.sh <dograh-dir> <venv-dir> <nexora-audio-wheel>
#
# - Dograh's API requirements first, then its Pipecat fork from the pinned checkout
#   (same extras as Dograh's Dockerfile, plus Pipecat's dev group for the test tools).
# - nexora-audio WITHOUT the [pipecat] extra: the extra would install Pipecat from PyPI
#   over Dograh's fork (decision D1).
# - Nothing is added to Dograh's requirements files (decision D2).
set -euo pipefail

die() { echo "setup.sh: $*" >&2; exit 1; }
[[ $# -eq 3 ]] || die "usage: setup.sh <dograh-dir> <venv-dir> <nexora-audio-wheel>"
dograh="$(cd "$1" && pwd)"
venv="$2"
wheel="$(realpath "$3")"
[[ -f "$dograh/api/requirements.txt" ]] || die "$dograh is not a Dograh checkout"
[[ -f "$dograh/pipecat/pyproject.toml" ]] || die "$dograh/pipecat missing (run fetch.sh)"
[[ -f "$wheel" ]] || die "wheel not found: $wheel"
command -v uv >/dev/null || die "uv is required (https://docs.astral.sh/uv/)"

PYTHON="${PYTHON:-python3.13}"
command -v "$PYTHON" >/dev/null || die "$PYTHON not found"

"$PYTHON" -m venv "$venv"
export VIRTUAL_ENV="$(cd "$venv" && pwd)"
export PATH="$VIRTUAL_ENV/bin:$PATH"

EXTRAS="cartesia,deepgram,openai,elevenlabs,groq,google,azure,sarvam,soundfile,silero,webrtc,speechmatics,openrouter,camb,mcp,inworld,smallest,aws-nova-sonic"

cd "$dograh"
uv pip install -r api/requirements.txt
uv pip install -r api/requirements.dev.txt
uv pip install -e "./pipecat[$EXTRAS]" --group pipecat/pyproject.toml:dev
uv pip uninstall opencv-python || true
uv pip install opencv-python-headless
# nexora-audio itself; its own dependencies come from PyPI, Pipecat stays the fork.
uv pip install "$wheel"

python - <<'PY'
import pathlib, pipecat
p = pathlib.Path(pipecat.__file__).resolve()
assert "pipecat/src" in str(p), f"pipecat resolves to {p}, not the Dograh fork"
print(f"setup.sh: ok (pipecat from {p.parent})")
PY
