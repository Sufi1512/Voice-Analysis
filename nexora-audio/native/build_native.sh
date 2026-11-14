#!/usr/bin/env bash
# Build the three bundled native libraries for the machine this runs on (Linux or macOS),
# from pinned sources, into $1/<platform-tag>/ with a provenance report.
#   native/build_native.sh out/
# Needs: a C compiler, make, curl, git, Rust (cargo), Python with meson + ninja (for
# WebRTC). The x86_64 Linux libraries in src/nexora_audio/_native were built the same way.
set -euo pipefail

OUT=${1:?usage: build_native.sh OUTDIR}
HERE=$(cd "$(dirname "$0")" && pwd)
WORK=$(mktemp -d)
OS=$(uname -s | tr '[:upper:]' '[:lower:]')
ARCH=$(uname -m); [ "$ARCH" = arm64 ] && ARCH=aarch64
TAG="$OS-$ARCH"
EXT=so; [ "$OS" = darwin ] && EXT=dylib
DEST="$OUT/$TAG"; mkdir -p "$DEST"
export MACOSX_DEPLOYMENT_TARGET=${MACOSX_DEPLOYMENT_TARGET:-11.0}

RNNOISE_URL=https://github.com/xiph/rnnoise/releases/download/v0.2/rnnoise-0.2.tar.gz
RNNOISE_SHA=90fce4b00b9ff24c08dbfe31b82ffd43bae383d85c5535676d28b0a2b11c0d37
DFN_REPO=https://github.com/Rikorose/DeepFilterNet.git
DFN_COMMIT=7b14b895fe7fc42cab72b4a4c1e49c982bd6404b

sha() { if command -v sha256sum >/dev/null; then sha256sum "$1" | cut -d' ' -f1; else shasum -a 256 "$1" | cut -d' ' -f1; fi; }
strip_lib() { if [ "$OS" = darwin ]; then strip -x "$1"; else strip --strip-unneeded "$1"; fi; }
set_id() { [ "$OS" = darwin ] && install_name_tool -id "@rpath/$(basename "$1")" "$1" || true; }

echo "== RNNoise v0.2"
curl -sSL -o "$WORK/rnnoise.tar.gz" "$RNNOISE_URL"
[ "$(sha "$WORK/rnnoise.tar.gz")" = "$RNNOISE_SHA" ] || { echo "rnnoise checksum mismatch"; exit 1; }
tar xzf "$WORK/rnnoise.tar.gz" -C "$WORK"
# v0.2's NEON/generic code includes a header the release does not ship (see the file)
[ -f "$WORK/rnnoise-0.2/src/os_support.h" ] || cp "$HERE/rnnoise-compat/os_support.h" "$WORK/rnnoise-0.2/src/"
( cd "$WORK/rnnoise-0.2"
  extra=""; [ "$ARCH" = x86_64 ] && extra="--enable-x86-rtcd"
  ./configure --disable-examples --disable-doc $extra CFLAGS="-O2" >/dev/null
  make -j4 >/dev/null )
if [ "$OS" = darwin ]; then cp "$WORK/rnnoise-0.2/.libs/librnnoise.0.dylib" "$DEST/librnnoise.dylib"
else cp "$WORK/rnnoise-0.2/.libs/librnnoise.so.0."* "$DEST/librnnoise.so"; fi

echo "== DeepFilterNet libdf @ $DFN_COMMIT"
git clone -q "$DFN_REPO" "$WORK/dfn" && git -C "$WORK/dfn" checkout -q "$DFN_COMMIT"
# not --locked: the Cargo.lock at this commit is out of date with its Cargo.toml files
( cd "$WORK/dfn" && RUSTFLAGS="--remap-path-prefix=$WORK=/build" \
    cargo build -q --release -p deep_filter --lib --no-default-features --features capi )
cp "$WORK/dfn/target/release/libdf.$EXT" "$DEST/libdf.$EXT"

echo "== nexora_aec (WebRTC AEC3)"
( cd "$HERE/nexora-aec" && CARGO_TARGET_DIR="$WORK/aec" cargo build -q --release --locked )
cp "$WORK/aec/release/libnexora_aec.$EXT" "$DEST/libnexora_aec.$EXT"

for f in "$DEST"/*."$EXT"; do strip_lib "$f"; set_id "$f"; done

{
  echo "platform: $TAG"
  echo "built: $(date -u +%Y-%m-%dT%H:%MZ) on $(uname -a)"
  echo "rustc: $(rustc --version)"
  echo "cc: $(cc --version | head -1)"
  for f in "$DEST"/*."$EXT"; do
    echo "$(basename "$f") sha256 $(sha "$f")"
    if [ "$OS" = linux ]; then
      echo "  newest glibc: $(objdump -T "$f" | grep -o 'GLIBC_[0-9.]*' | sort -V | tail -1)"
      echo "  needs: $(objdump -p "$f" | awk '/NEEDED/{print $2}' | tr '\n' ' ')"
    else
      echo "  minos: $(otool -l "$f" | awk '/minos/{print $2; exit}')"
      echo "  links: $(otool -L "$f" | tail -n +2 | awk '{print $1}' | tr '\n' ' ')"
    fi
  done
} | tee "$DEST/BUILD_INFO.txt"
