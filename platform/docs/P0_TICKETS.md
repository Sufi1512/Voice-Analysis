# P0 Foundations: tickets

From `P0_SPEC.md` and `P0_IMPLEMENTATION_DECISIONS.md` (AC-1 to AC-9). Branch `platform/p0-foundations`.

| Ticket | Title | Depends on | Size |
|---|---|---|---|
| T1 | Lay out `platform/` and pin Dograh in `ENGINE.lock` | none | S |
| T2 | `fetch.sh`: pinned read-only checkout with our patches | T1 | M |
| T3 | `setup.sh`: Dograh API environment with the nexora-audio wheel; Dograh's own tests pass | T2 | M |
| T4 | nexora engine contract tests | T3 | M |
| T5 | Exit test: a Dograh call pipeline with nexora-audio | T4 | M |
| T6 | Telemetry off with `nexora.env` | T3 | S |
| T7 | CI workflow `platform.yml` with test job and image build | T5, T6 | M |
| T8 | P1 and Workflow Runner specs, LangGenius enquiry draft | T7 | M |

## Coverage
| Criterion | Tickets |
|---|---|
| AC-1 pinned checkout with patches | T1, T2 |
| AC-2 drift fails loudly | T2 |
| AC-3 Dograh's own tests pass | T3 |
| AC-4 factory builds wrapped nexora filter per call | T4 |
| AC-5 engine contract (pace, noise, speech, disable, chunk sizes, start/stop, budget) | T4 |
| AC-6 exit test | T5 |
| AC-7 telemetry off | T6 |
| AC-8 CI | T7 |
| AC-9 empty service folders with READMEs | T1 |
| P0_SPEC §6 documents | T8 |

---

### T1: Lay out `platform/` and pin Dograh in `ENGINE.lock`
Depends on: none
Spec: P0_SPEC §1, §2; AC-1 (pins), AC-9

**What**: Create `platform/engines/dograh/` with `ENGINE.lock`, `patches/0001-nexora-noise-engine.patch` (copied from `integrations/dograh/`), README; create `services/`, `apps/`, `packages/`, `sdks/` with READMEs.

**Acceptance criteria**
- [ ] `ENGINE.lock` holds the Dograh and Pipecat repository URLs and full commit SHAs from P0_SPEC §2.
- [ ] The patch is byte-identical to `integrations/dograh/0001-nexora-noise-engine.patch`.
- [ ] Each empty folder has a README naming what goes there and from which phase.

**Tests to write first**
- `test_engine_lock_pins_audited_commits` (unit)
- `test_patch_matches_integration_copy` (unit)
- `test_platform_folders_have_readmes` (unit)

**Notes**: tests in `platform/engines/dograh/tests/test_layout.py`; run with plain pytest, no Dograh needed.

### T2: `fetch.sh`: pinned read-only checkout with our patches
Depends on: T1
Spec: P0_SPEC ground rules; AC-1, AC-2; D5

**What**: `fetch.sh <dir>` clones Dograh and its Pipecat submodule at the pinned commits (HTTPS, depth 1, detached), checks every patch with `git apply --check`, then applies them.

**Acceptance criteria**
- [ ] Given an empty target, when `fetch.sh` runs, then `HEAD` of Dograh and of `pipecat/` equal the pinned SHAs and the patched factory contains the `nexora` engine.
- [ ] Given a patch that does not apply, then `fetch.sh` exits non-zero, prints the patch name, and applies nothing.
- [ ] Given an existing target directory, then `fetch.sh` refuses unless it is empty (no silent overwrite).

**Tests to write first**
- `test_fetch_applies_patches_at_pinned_commits` (integration, network; marked `network`)
- `test_fetch_fails_loudly_on_drift` (integration; uses a local bare repo fixture and a broken patch, no network)
- `test_fetch_refuses_non_empty_target` (unit)

**Notes**: `set -euo pipefail`; read pins from `ENGINE.lock`; allow overriding the patch dir and repo URLs by environment variable only for tests.

### T3: `setup.sh`: Dograh API environment; Dograh's own tests pass
Depends on: T2
Spec: P0_SPEC §4.1; AC-3; D1, D2, D6

**What**: `setup.sh <dograh-dir> <venv>` creates a Python 3.13 venv, installs Dograh's `api/requirements.txt`, the pinned Pipecat fork from the checkout with only the needed extras, and the nexora-audio wheel without extras; `run-tests.sh` runs Dograh's noise-reduction and workflow-configuration tests.

**Acceptance criteria**
- [ ] `import pipecat` resolves to the checkout's Pipecat, not PyPI.
- [ ] `api/tests/test_noise_reduction.py` and the workflow-configuration tests pass on the patched tree.

**Tests to write first**
- `test_pipecat_is_dograh_fork` (integration)
- Dograh's own suites as the integration check

**Notes**: Dograh tests need dummy `DATABASE_URL`/`REDIS_URL`; keep them in `run-tests.sh`, not in Dograh.

### T4: nexora engine contract tests
Depends on: T3
Spec: P0_SPEC §4.2; AC-4, AC-5

**What**: `platform/engines/dograh/tests/test_nexora_engine.py`, copied into `api/tests/nexora/` at test time (D8), using Dograh's real factory.

**Acceptance criteria**
- [ ] AC-4 and every clause of AC-5.

**Tests to write first**
- `test_factory_wraps_nexora_in_safe_filter`, `test_new_instance_per_call`, `test_keeps_pace[8000|16000]`, `test_removes_stationary_noise[8000|16000]`, `test_keeps_clean_speech`, `test_disable_frame_passes_through`, `test_any_chunk_size`, `test_passes_audio_outside_start_stop`, `test_under_safe_filter_budget` (integration)

**Notes**: synthetic signals only (noise, harmonic "speech"), seeded. Budget measured as p95 and max per frame; report both.

### T5: Exit test: a Dograh call pipeline with nexora-audio
Depends on: T4
Spec: P0_SPEC §4.3; AC-6

**What**: a pipeline built the way Dograh builds calls, with a test input transport whose `audio_in_filter` comes from Dograh's `build_audio_in_filter` with the agent's `noise_reduction`, a recording stub STT and a stub LLM; noisy speech in; end-of-call frame.

**Acceptance criteria**
- [ ] AC-6.

**Tests to write first**
- `test_call_pipeline_cleans_audio_before_stt` (integration)
- `test_safe_filter_never_trips_during_call` (integration)
- `test_call_ends_normally` (integration)

**Notes**: use Dograh's `api/tests/pipecat_test_utils.py` helpers where they fit; if Dograh's engine wiring needs a database, build the transport and pipeline with Dograh's factory and Pipecat's pipeline runner directly and say so in the test docstring.

### T6: Telemetry off with `nexora.env`
Depends on: T3
Spec: P0_SPEC §2; AC-7

**What**: `platform/engines/dograh/nexora.env` with `ENABLE_TELEMETRY=false`, `DEPLOYMENT_MODE=oss`, no PostHog key; a test loads Dograh's `api.constants` under it.

**Acceptance criteria**
- [ ] AC-7, and Dograh's app-level telemetry switch evaluates to off.

**Tests to write first**
- `test_env_nexora_turns_telemetry_off` (integration)
- `test_env_nexora_has_no_secrets` (unit)

### T7: CI workflow `platform.yml`
Depends on: T5, T6
Spec: P0_SPEC §5; AC-8; D4

**What**: on `platform/**`, `nexora-audio/**`, or the workflow itself: build wheel → `fetch.sh` → `setup.sh` → `run-tests.sh` (T3–T6) on `ubuntu-latest`; second job builds Dograh's API image from the patched tree with the wheel installed.

**Acceptance criteria**
- [ ] AC-8; no macOS job; no step pushes anywhere.

**Tests to write first**
- `test_workflow_has_no_push_or_macos` (unit, parses the YAML)

### T8: P1 and Workflow Runner specs, LangGenius enquiry draft
Depends on: T7
Spec: P0_SPEC §6

**What**: `platform/docs/P1_SPEC.md`, `platform/docs/WORKFLOW_RUNNER_SPEC.md` (drafts for approval), `platform/docs/LANGGENIUS_ENQUIRY_DRAFT.md` (not sent).

**Acceptance criteria**
- [ ] Each spec has scope, acceptance criteria and open questions, and is marked "draft, waiting for approval".
- [ ] The enquiry is a draft only; nothing is sent.
