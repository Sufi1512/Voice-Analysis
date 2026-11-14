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
| Built | 2026-11-14 (rebuilt in the bug round), Ubuntu 24.04, rustc 1.97.0, by `native/build_native.sh` (crates resolved from the repo's Cargo.lock; tract 0.21.4) |
| Build | `cargo build --release -p deep_filter --lib --no-default-features --features capi` with build paths remapped, `strip --strip-unneeded` |
| Runtime deps | libc, libm, libgcc_s; newest glibc symbol `GLIBC_2.35` (Ubuntu 22.04+, Debian 12+). Older systems fall back to RNNoise |
| Output sha256 | `e7328e109b60c835d4aed8ec9fe9b21c58f94f54c0ac1a64960b1c309a3ad6ee` |
| Reproducible | No: two builds with the same script, machine and folder differ (inside DeepFilterNet's own thin-LTO build; OPEN_ISSUES I-023) |
| Source changes | none (macOS builds patch tract-linalg so Apple AMX is opt-in: `native/tract-linalg-0.21.4-amx-opt-in.patch`, OPEN_ISSUES I-031) |

## linux-x86_64/libnexora_aec.so (WebRTC AEC3 echo canceller)
| Field | Value |
|---|---|
| Upstream | WebRTC AudioProcessing **v2.1** (PulseAudio's standalone `webrtc-audio-processing`), bundled in crate `webrtc-audio-processing-sys` 2.1.0 (crates.io), driven by crate `webrtc-audio-processing` 2.1.0 (features `bundled`, `experimental-aec3-config`) |
| Also compiled in | Abseil `20240722.0` (Apache-2.0), GitHub release tarball sha256 `f50e5ac311a81382da7fa75b97310e4b9006474f9560ac46f54a9967f07d4ae3`, with Meson wrapdb patch `abseil-cpp_20240722.0-3` sha256 `12dd8df1488a314c53e3751abd2750cf233b830651d168b6a9f15e7d0cf71f7b` (both as pinned in the upstream wrap file) |
| Our code | `nexora-audio/native/nexora-aec/`: a C API (`src/lib.rs`, BSD-3) and a glibc compatibility shim (`csrc/compat.c`: defines `__isoc23_sscanf` over `vsscanf` so the library loads on glibc 2.34+ instead of 2.38+) |
| Licences | WebRTC: BSD-3-Clause (Google). Abseil: Apache-2.0. See `../THIRD_PARTY_NOTICES.md` |
| Built | 2026-11-14 (rebuilt in the bug round: the previous binary predated the glibc shim fix), Ubuntu 24.04, rustc 1.97.0 (2d8144b78 2026-07-07), Meson 1.12.1, gcc 13.3.0, by `native/build_native.sh` |
| Build | `cd native/nexora-aec && cargo build --release --locked` with build paths remapped, `strip` |
| Runtime deps | libc, libm, libgcc_s, libstdc++ (`GLIBCXX_3.4.30`, gcc 12+); newest glibc symbol `GLIBC_2.34` (Ubuntu 22.04+, Debian 12+) |
| Output sha256 | `c570a49ce6c7c5cf04b8f702679c11985aa1313ef3c7df89a55cb8deac319c10` (reproducible: two builds byte-identical) |
| Source changes | none to WebRTC or Abseil |

## ../_models/DeepFilterNet3_onnx.tar.gz
Official model from `models/` in the same commit, sha256
`c94d91f70911001c946e0fabb4aa9adc37045f45a03b56008cb0c8244cb63616`, unchanged.

## ../_models/silero_vad.onnx
From the `silero-vad` 6.2.3 wheel on PyPI (`silero_vad/data/silero_vad.onnx`), MIT,
sha256 `1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3`, unchanged.

## ../_models/smart-turn-v3.2-cpu.onnx and ../backends/_whisper_features.py
From the `pipecat-ai` 1.16.0 wheel on PyPI (`pipecat/audio/turn/smart_turn/data/` and
`pipecat/audio/turn/smart_turn/_whisper_features.py`), BSD-2-Clause (Daily; the feature code
has Apache-2.0 Hugging Face portions). Model sha256
`2bb026316b14a660486a75b1733cd3fbab8c2fd0314dc9af7be49f8cca967e4f`, both unchanged.

Linux aarch64, macOS x86_64 and macOS arm64 libraries are built in CI from the same pinned
sources by `native/build_native.sh` (each wheel carries its platform's `BUILD_INFO.txt`); see
`docs/E7_SPEC.md`. macOS builds patch tract-linalg 0.21.4 so Apple's AMX instructions are
opt-in (`TRACT_APPLE_AMX=1`): they crashed in virtual machines (OPEN_ISSUES I-031). Windows is
not built yet. Point
`NEXORA_DEEPFILTER_LIBRARY` at a libdf built with the command above, and/or
`NEXORA_RNNOISE_LIBRARY` at a librnnoise built from the same RNNoise release (or install
the system package `librnnoise0` on Debian/Ubuntu).
