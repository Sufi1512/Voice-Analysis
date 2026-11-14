# P0 Foundations: implementation decisions

Status: Approved (P0 spec approved by the user on 2026-11-14)   ·   Date: 2026-11-14   ·   Owner: NEXORA platform

Companion to `P0_SPEC.md`, which stays the approved spec. This file records the choices made
while turning it into code, and lists every acceptance criterion in one place so the tickets
(`P0_TICKETS.md`) and tests can point at them.

## Problem and goal
Prove that NEXORA can change Dograh without forking it: a Dograh call pipeline runs with the
`nexora` noise engine, in CI, on Linux. Success = the exit test (AC-6) passes in
`.github/workflows/platform.yml` on `ubuntu-latest`.

## Scope
### In scope
- `platform/engines/dograh/`: `ENGINE.lock`, `fetch.sh`, `patches/`, `tests/`, `nexora.env`, README.
- Empty `platform/services/`, `apps/`, `packages/`, `sdks/` with a README each.
- Tests 1–4 from P0_SPEC §4.
- `.github/workflows/platform.yml`: test job and Dograh API image build job.
- After the code: P1 (NEXORA Core) spec, Workflow Runner spec, LangGenius licence enquiry draft.

### Out of scope
- Real telephony calls; the full Docker Compose stack in CI (P2).
- macOS (Linux only).
- Any push to `Sufi1512/dograh`, `Sufi1512/dify`, `dograh-hq/pipecat` or upstream projects.

## Decisions
| # | Decision | Reason |
|---|---|---|
| D1 | Install nexora-audio **without** its `[pipecat]` extra | The extra would install Pipecat from PyPI over Dograh's own Pipecat fork (P0_SPEC §3 says `nexora-audio[pipecat]`; this corrects it, as `integrations/dograh/README.md` already warns) |
| D2 | Do not add nexora-audio to Dograh's `api/requirements.txt`; CI and the image build install the locally built wheel after Dograh's requirements | A path to a local wheel in Dograh's requirements would break Dograh's normal installs; keeps the patch to code and schema only |
| D3 | The canonical patch is `platform/engines/dograh/patches/0001-nexora-noise-engine.patch`, copied unchanged from `integrations/dograh/` | P0_SPEC §1 layout. `integrations/dograh/` belongs to the audio session and is left untouched; removing the duplicate is a follow-up for whoever owns it |
| D4 | Python 3.13, `ubuntu-latest` | Matches Dograh's `api/Dockerfile` (`python:3.13-slim`); user rule: Linux only |
| D5 | `fetch.sh` clones over HTTPS with `--depth 1` at the pinned commits, detached, and fails if `git apply --check` fails | Read-only, reproducible, loud on upstream drift (P0_SPEC ground rules) |
| D6 | Pipecat is installed editable from the pinned checkout with **the same extras as Dograh's Dockerfile and `scripts/setup_requirements.sh`**, plus Pipecat's dev group for test tools | Dograh's API modules import many provider services at import time, so a trimmed extra set would test a configuration Dograh never runs. Install is quick with uv's cache (P0_SPEC risk 3 handled by caching, not by trimming) |
| D7 | Work on branch `platform/p0-foundations` with its own pull request; never push to `main` directly | Another session works in the same repository |
| D8 | NEXORA's own tests live in `platform/engines/dograh/tests/` and are copied into the Dograh checkout's `api/tests/nexora/` at test time | They use Dograh's imports and fixtures without changing Dograh's test files beyond the patch |
| D9 | The exit test enters through Dograh's Twilio `create_transport` with a fake Twilio WebSocket (real-time 8 kHz mu-law media events), not `api/tests/pipecat_test_utils.py` | Pipecat's mock input transport skips `audio_in_filter`, so it cannot prove the filter runs. Dograh's real call entry point covers the serializer, `build_audio_in_filter` and the input transport; only the credential lookup and the Twilio REST hangup are stubbed |
| D10 | NEXORA's Dograh settings file is `nexora.env`, not `.env.nexora` | The repository's root `.gitignore` drops `.env.*` (correctly, for secrets), so the dot name never reached CI. A test checks the file is committed and holds no secrets |

## Acceptance criteria
- [ ] **AC-1** Given `ENGINE.lock`, when `fetch.sh <dir>` runs, then Dograh is checked out at `d672de2947da691fbc4542b62b914547a80e01ab` and Pipecat at `9ac08e90be4bb83e506f3d10deaa8e6d31588547`, and every patch in `patches/` is applied.
- [ ] **AC-2** Given a patch that no longer applies, when `fetch.sh` runs, then it exits non-zero, names the patch and leaves no half-applied tree.
- [ ] **AC-3** Given the patched checkout, when Dograh's `api/tests/test_noise_reduction.py` and its workflow-configuration tests run, then they pass.
- [ ] **AC-4** Given the factory configured with `{enabled: true, engine: "nexora"}`, then it returns a `SafeAudioFilter` wrapping `NexoraAudioFilter`, and a new instance per call.
- [ ] **AC-5** Given the nexora engine, then at 8 and 16 kHz with 20 ms chunks: output keeps pace with input (only the processing delay missing); stationary noise drops by at least 10 dB; clean speech keeps its level within 3 dB; a disable frame passes audio through unchanged; any chunk size works; audio before `start` and after `stop` passes through; the 95th-percentile per-frame time stays under `SafeAudioFilter`'s 10 ms budget and the filter is never switched off.
- [ ] **AC-6 (exit test)** Given a Dograh call pipeline with a test transport, stubbed STT and LLM, and the agent's `noise_reduction` set to `{enabled: true, engine: "nexora"}`, when noisy speech is sent in, then the audio reaching STT is nexora-audio's output (noise reduced by at least 10 dB, speech kept), `SafeAudioFilter` never tripped, and the call ends normally.
- [ ] **AC-7** Given `nexora.env`, when Dograh's API settings load, then `ENABLE_TELEMETRY` is false and no PostHog key is set.
- [ ] **AC-8** Given a change under `platform/**` or `nexora-audio/**`, when CI runs `platform.yml` on `ubuntu-latest`, then the wheel builds, `fetch.sh` succeeds, AC-3 to AC-7 pass, and the patched Dograh API Docker image builds.
- [ ] **AC-9** `platform/services/`, `apps/`, `packages/`, `sdks/` exist with READMEs saying what goes there and from which phase.

## Open questions
- Who removes the duplicate `integrations/dograh/` (audio session or platform session)? Not blocking.
