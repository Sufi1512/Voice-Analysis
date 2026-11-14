# E7: packaging and devices (spec and results)

Phase E7 of `nexora-server/docs/ENTERPRISE_PLAN.md`, built 2026-11-14 on the user's
instruction to build the remaining phases in order. Acceptance: `pip install` works on each
platform and the test suite passes there; a live device demo runs.

## 1. Native libraries for every platform

`native/build_native.sh` builds the three bundled libraries for the machine it runs on, from
pinned sources, with a `BUILD_INFO.txt` (hashes, newest glibc symbol or macOS minimum, links):

- **RNNoise** v0.2 release archive (sha256 checked). Its ARM/generic code includes a header
  the release does not ship; `native/rnnoise-compat/os_support.h` stands in.
- **DeepFilterNet libdf** at the pinned commit (built unlocked: the commit's lock file is
  stale), with build paths remapped.
- **libnexora_aec** (WebRTC AEC3) from `native/nexora-aec`, with a glibc shim linked
  whole-archive on Linux so it loads on glibc 2.34+.

On Linux x86_64 it rebuilds the bundled RNNoise and AEC libraries byte for byte.

| Platform | Built and tested on (CI) | Tests | Notes |
| --- | --- | --- | --- |
| linux-x86_64 | committed binaries; voice-quality CI | all pass | `manylinux_2_35` |
| linux-aarch64 | GitHub `ubuntu-24.04-arm` | 190 passed | glibc 2.34 (AEC), 2.35 (libdf) |
| darwin-x86_64 | GitHub `macos-15-intel` | 190 passed | macOS 11+ |
| darwin-aarch64 | GitHub `macos-15` (Apple Silicon) | 170 passed, 22 skipped, 1 expected fail | **libdf crashes with an illegal instruction** (I-031): ships without it, noise removal falls back to RNNoise; AEC3 slightly weaker in one test (I-033) |

Workflows: `.github/workflows/native-libs.yml` (build + test per platform) and
`.github/workflows/wheels.yml` (one platform-tagged wheel per platform, built with
`NEXORA_WHEEL_PLATFORM` via `hatch_build.py` so each wheel carries only its own libraries,
installed into a clean virtualenv and tested).

## 2. Live microphone and speaker streaming

`nexora_audio.devices` (`pip install nexora-audio[devices]`; Linux also needs
`libportaudio2`):

- `LiveSession`: one full-duplex sound-card stream; the callback only copies into
  lock-free single-producer/single-consumer ring buffers; a worker thread runs the
  `StreamSession` on 20 ms chunks. `monitor=True` plays your cleaned voice (demo);
  `monitor=False` plays what you `play()` (the agent) and uses it as the sample-aligned echo
  reference. Dropouts counted (input overflow, output underrun, device flags).
- `StreamSession(judge_in_background=True)` (used by `LiveSession`): Smart Turn runs on its
  own thread, so a pause never stalls the audio thread ~45 ms. Decisions are identical to
  in-line (tested).
- `nexora-audio devices | live | process` command.
- Tests on a simulated real-time sound card: 10 s (60 s opt-in) with no dropouts, cleaned
  audio in monitor mode, agent mode playback and echo reference.

## Not done (OPEN_ISSUES.md)

Real hardware (I-024: run `pytest -m device` and `nexora-audio live` on your machine), libdf
on Apple Silicon (I-031), Windows (not attempted).

## Verification

- `native-libs` run 43581702719: build + full test suite on linux-aarch64, darwin-x86_64,
  darwin-aarch64 (counts in the table above).
- `wheels` run 43583904866: all four platform wheels built, installed into a clean
  virtualenv and tested.

## macOS paused (2026-11-14)

NEXORA is integrated into Python services on Linux, so the macOS builds were taken out of
CI (`native-libs.yml`, `wheels.yml`). Before that, the bug round fixed DeepFilterNet on Apple
Silicon (I-031: tract's AMX instructions, now opt-in through a build patch) and the arm64 macOS
wheel passed its tests with it. `native/build_native.sh` still builds on macOS; add the
`macos-15` / `macos-15-intel` matrix rows back to resume.
