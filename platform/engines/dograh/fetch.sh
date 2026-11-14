#!/usr/bin/env bash
# Clone Dograh and its Pipecat fork read only at the commits in ENGINE.lock, then apply
# NEXORA's patches. Fails loudly (and leaves the tree unpatched) if any patch no longer
# applies. Never pushes anywhere.
#
# Usage: fetch.sh <empty-or-missing-target-dir>
# Test-only overrides: NEXORA_ENGINE_LOCK (lock file), NEXORA_PATCH_DIR (patch folder).
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
lock="${NEXORA_ENGINE_LOCK:-$here/ENGINE.lock}"
patch_dir="${NEXORA_PATCH_DIR:-$here/patches}"

die() { echo "fetch.sh: $*" >&2; exit 1; }

[[ $# -eq 1 ]] || die "usage: fetch.sh <target-dir>"
target="$1"

if [[ -e "$target" ]]; then
  [[ -d "$target" ]] || die "$target exists and is not a directory"
  [[ -z "$(ls -A "$target")" ]] || die "$target is not empty; refusing to overwrite"
fi

read_lock() {
  local key="$1" value
  value="$(grep -E "^${key}=" "$lock" | head -n1 | cut -d= -f2-)"
  [[ -n "$value" ]] || die "$key missing in $lock"
  printf '%s' "$value"
}
DOGRAH_REPO="$(read_lock DOGRAH_REPO)"
DOGRAH_COMMIT="$(read_lock DOGRAH_COMMIT)"
PIPECAT_REPO="$(read_lock PIPECAT_REPO)"
PIPECAT_COMMIT="$(read_lock PIPECAT_COMMIT)"
[[ "$DOGRAH_COMMIT" =~ ^[0-9a-f]{40}$ ]] || die "DOGRAH_COMMIT is not a full SHA"
[[ "$PIPECAT_COMMIT" =~ ^[0-9a-f]{40}$ ]] || die "PIPECAT_COMMIT is not a full SHA"

checkout() {  # checkout <repo-url> <sha> <dir>
  local url="$1" sha="$2" dir="$3"
  mkdir -p "$dir"
  git -C "$dir" init -q
  git -C "$dir" remote add origin "$url"
  # Read only: make any accidental push fail.
  git -C "$dir" remote set-url --push origin "no-push://read-only"
  git -C "$dir" fetch -q --depth 1 origin "$sha"
  git -C "$dir" -c advice.detachedHead=false checkout -q FETCH_HEAD
  local got
  got="$(git -C "$dir" rev-parse HEAD)"
  [[ "$got" == "$sha" ]] || die "$url: expected $sha, got $got"
}

echo "fetch.sh: Dograh $DOGRAH_COMMIT"
checkout "$DOGRAH_REPO" "$DOGRAH_COMMIT" "$target"
echo "fetch.sh: Pipecat $PIPECAT_COMMIT"
rm -rf "$target/pipecat"
checkout "$PIPECAT_REPO" "$PIPECAT_COMMIT" "$target/pipecat"

shopt -s nullglob
patches=("$patch_dir"/*.patch)
shopt -u nullglob

restore() {
  git -C "$target" checkout -q -- .
  git -C "$target" clean -qfd -e pipecat
}

errlog="$(mktemp)"
trap 'rm -f "$errlog"' EXIT

for p in "${patches[@]}"; do
  name="$(basename "$p")"
  if ! git -C "$target" apply --check "$p" 2>"$errlog"; then
    cat "$errlog" >&2
    restore
    die "patch $name no longer applies to Dograh $DOGRAH_COMMIT; nothing was applied"
  fi
  git -C "$target" apply "$p"
  echo "fetch.sh: applied $name"
done
echo "fetch.sh: ok (${#patches[@]} patches)"
