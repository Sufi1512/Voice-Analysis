# Bundled native libraries

## linux-x86_64/librnnoise.so
| Field | Value |
|---|---|
| Upstream | https://github.com/xiph/rnnoise, release **v0.2** (library version 0.4.1) |
| Source archive | `rnnoise-0.2.tar.gz` from the GitHub release, sha256 `90fce4b00b9ff24c08dbfe31b82ffd43bae383d85c5535676d28b0a2b11c0d37` |
| Model | Default model shipped in the release archive (`src/rnnoise_data.c`), no changes |
| Licence | BSD-3-Clause (see `../THIRD_PARTY_NOTICES.md`) |
| Built | 2026-11-13, Ubuntu 24.04, gcc 13.3.0 |
| Build | `./configure --disable-examples --disable-doc --enable-x86-rtcd CFLAGS="-O2"` then `make`, `strip --strip-unneeded` |
| Runtime deps | libc, libm only; newest glibc symbol `GLIBC_2.14` (manylinux2014-compatible) |
| Output sha256 | `adf8304051ba16472726aa33ec10ae024dbbdb38c6caf5ea5c4408247ccf25e2` |
| Source changes | none |

## linux-x86_64/libdf.so (DeepFilterNet C API)
| Field | Value |
|---|---|
| Upstream | https://github.com/Rikorose/DeepFilterNet, commit `7b14b895fe7fc42cab72b4a4c1e49c982bd6404b` (crate `deep_filter` 0.5.7-pre) |
| Licence | MIT OR Apache-2.0 (used under MIT) |
| Built | 2026-11-13, Ubuntu 24.04, rustc 1.97.0, crates from crates.io via the repo's Cargo.lock |
| Build | `cargo build --release -p deep_filter --lib --no-default-features --features capi`, `strip --strip-unneeded` |
| Runtime deps | libc, libm, libgcc_s; newest glibc symbol `GLIBC_2.35` (Ubuntu 22.04+, Debian 12+). Older systems fall back to RNNoise |
| Output sha256 | `c9a27d2d658bc11c1377fd8ce4c2882817289e3c6cccee581ae6099352612d9c` |
| Source changes | none |

## ../_models/DeepFilterNet3_onnx.tar.gz
Official model from `models/` in the same commit, sha256
`c94d91f70911001c946e0fabb4aa9adc37045f45a03b56008cb0c8244cb63616`, unchanged.

## ../_models/silero_vad.onnx
From the `silero-vad` 6.2.3 wheel on PyPI (`silero_vad/data/silero_vad.onnx`), MIT,
sha256 `1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3`, unchanged.

Other platforms (macOS, Windows, Linux aarch64) are not bundled yet. Point
`NEXORA_DEEPFILTER_LIBRARY` at a libdf built with the command above, and/or
`NEXORA_RNNOISE_LIBRARY` at a librnnoise built from the same RNNoise release (or install
the system package `librnnoise0` on Debian/Ubuntu).
