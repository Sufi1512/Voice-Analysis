#!/usr/bin/env bash
# Run Dograh's own tests for the parts NEXORA changes, then NEXORA's tests, against the
# patched checkout made by fetch.sh and the environment made by setup.sh.
#
# Usage: run-tests.sh <dograh-dir> <venv-dir> [extra pytest args]
set -euo pipefail

die() { echo "run-tests.sh: $*" >&2; exit 1; }
[[ $# -ge 2 ]] || die "usage: run-tests.sh <dograh-dir> <venv-dir> [pytest args]"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
dograh="$(cd "$1" && pwd)"
venv="$(cd "$2" && pwd)"
shift 2

# NEXORA's in-Dograh tests live in our repo and are copied in at test time (decision D8).
rm -rf "$dograh/api/tests/nexora"
cp -r "$here/tests/in_dograh" "$dograh/api/tests/nexora"

# NEXORA's settings (telemetry off), plus the dummies Dograh's own CI uses for imports.
set -a
# shellcheck disable=SC1091
source "$here/.env.nexora"
set +a
export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://dummy:dummy@localhost/dummy}"
export REDIS_URL="${REDIS_URL:-redis://localhost:6379/0}"
export MINIO_PUBLIC_ENDPOINT="${MINIO_PUBLIC_ENDPOINT:-http://localhost:9000}"
export ENVIRONMENT=test
export PYTHONPATH="$dograh"
export NEXORA_ENV_FILE="$here/.env.nexora"

cd "$dograh/api"
"$venv/bin/python" -m pytest -q -p no:cacheprovider \
  tests/test_noise_reduction.py \
  tests/test_workflow_configurations_schema.py \
  tests/test_workflow_configuration_policy.py \
  tests/nexora \
  "$@"
