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

Other platforms (macOS, Windows, Linux aarch64) are not bundled yet. Set
`NEXORA_RNNOISE_LIBRARY` to a librnnoise built from the same source, or install
the system package (`librnnoise0` on Debian/Ubuntu).
