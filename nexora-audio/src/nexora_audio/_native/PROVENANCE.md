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

## linux-x86_64/libnexora_aec.so (WebRTC AEC3 echo canceller)
| Field | Value |
|---|---|
| Upstream | WebRTC AudioProcessing **v2.1** (PulseAudio's standalone `webrtc-audio-processing`), bundled in crate `webrtc-audio-processing-sys` 2.1.0 (crates.io), driven by crate `webrtc-audio-processing` 2.1.0 (features `bundled`, `experimental-aec3-config`) |
| Also compiled in | Abseil `20240722.0` (Apache-2.0), GitHub release tarball sha256 `f50e5ac311a81382da7fa75b97310e4b9006474f9560ac46f54a9967f07d4ae3`, with Meson wrapdb patch `abseil-cpp_20240722.0-3` sha256 `12dd8df1488a314c53e3751abd2750cf233b830651d168b6a9f15e7d0cf71f7b` (both as pinned in the upstream wrap file) |
| Our code | `nexora-audio/native/nexora-aec/`: a C API (`src/lib.rs`, BSD-3) and a glibc compatibility shim (`csrc/compat.c`: defines `__isoc23_sscanf` over `vsscanf` so the library loads on glibc 2.34+ instead of 2.38+) |
| Licences | WebRTC: BSD-3-Clause (Google). Abseil: Apache-2.0. See `../THIRD_PARTY_NOTICES.md` |
| Built | 2026-11-13, Ubuntu 24.04, rustc 1.97.0 (2d8144b78 2026-07-07), Meson 1.12.1, gcc 13.3.0 |
| Build | `cd native/nexora-aec && cargo build --release` (Cargo.lock included), `strip` |
| Runtime deps | libc, libm, libgcc_s, libstdc++ (`GLIBCXX_3.4.30`, gcc 12+); newest glibc symbol `GLIBC_2.34` (Ubuntu 22.04+, Debian 12+) |
| Output sha256 | `5c8dda82709fff8a2c5a3ab73b05545dcdfb2eced15d1ce3f508f7551e7042ae` |
| Source changes | none to WebRTC or Abseil |

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
