# P0 Foundations: specification (for approval)

Phase P0 of the NEXORA AI plan ("NEXORA AI – Platform Analysis & Plan", roadmap). Status:
**draft, waiting for approval** (project rule: no implementation before the spec is approved).

**Exit test (from the plan):** a Dograh call runs with nexora-audio in CI.

## Ground rules

- **Nothing is pushed to Dograh, Pipecat or Dify.** Their repositories are only read: cloned at
  a pinned commit during the build. Everything NEXORA writes lives in this repository
  (`Sufi1512/Voice-Analysis`), under `platform/`.
- NEXORA's changes to Dograh are **small patch files** kept here and applied to a clean
  checkout at build time. If upstream changes under them, the build fails loudly
  (`git apply --check`), never silently.
- Licences: Dograh and its Pipecat fork are BSD-2-Clause; patching and redistributing them is
  allowed with their notices kept.

## 1. Repository layout (the plan's monorepo, started)

```
platform/
  README.md                  what lives where, how to build and test
  docs/                      audits, specs (this file), later Core and Runner specs
  engines/dograh/
    ENGINE.lock              pinned commits: Dograh d672de29..., Pipecat 9ac08e90...
    fetch.sh                 clone both read-only at those commits, apply our patches
    patches/                 NEXORA's changes to Dograh (see 3)
    tests/                   NEXORA's tests, run against the patched Dograh
    .env.nexora              NEXORA's Dograh settings (telemetry off, see 2)
  services/ apps/ packages/ sdks/   created empty with READMEs; filled from P1 on
```

The existing `nexora-audio`, `nexora-server` and `nexora-client` stay where they are.

## 2. Dograh pinned, telemetry off

| | Pinned |
| --- | --- |
| Dograh | `github.com/Sufi1512/dograh` @ `d672de2947da691fbc4542b62b914547a80e01ab` (the audited commit) |
| Pipecat (Dograh's submodule) | `github.com/dograh-hq/pipecat` @ `9ac08e90be4bb83e506f3d10deaa8e6d31588547` |

Telemetry needs no code change: Dograh reads it from the environment. NEXORA's settings file
sets `ENABLE_TELEMETRY=false` and no `POSTHOG_API_KEY`; a test checks the patched Dograh
starts with telemetry off under those settings.

## 3. The `nexora` noise engine in Dograh

Dograh already has the hook: `api/services/pipecat/noise_reduction/factory.py` keeps a table of
engines (today only `rnnoise`), and every engine is wrapped in Dograh's `SafeAudioFilter`, which
passes audio through unchanged if the engine fails or runs over its time budget, so a filter
fault never drops a call.

The patch (about 10 lines):

- `api/schemas/workflow_configurations.py`: the engine choice becomes `"rnnoise" | "nexora"`.
- `factory.py`: registers `nexora` → `nexora_audio.integrations.pipecat.NexoraAudioFilter`
  (already in nexora-audio: runs a `StreamSession` per call in a worker thread, without turn
  events, since Pipecat does its own turn-taking).
- `ui/src/types/workflow-configurations.ts` and the generated client type: the agent's
  noise-removal setting offers `nexora`.
- `api/requirements.txt`: `nexora-audio[pipecat]`, installed from this repository's wheel.

Dograh's default stays "noise reduction off" per agent, as upstream. NEXORA turns `nexora`
on when it creates agents (from P2, through the gateway).

## 4. Tests

Run in CI against the pinned, patched Dograh:

1. **Dograh's own tests still pass** where they touch what we change:
   `api/tests/test_noise_reduction.py` (factory, `SafeAudioFilter`, RNNoise) and the
   workflow-configuration tests.
2. **The nexora engine meets the same contract as RNNoise** (new file in
   `platform/engines/dograh/tests/`): built by the factory when configured and wrapped in
   `SafeAudioFilter`; a fresh instance per call; keeps pace with 20 ms telephony chunks at
   8 and 16 kHz; removes stationary noise; keeps clean speech; disable frame passes audio
   through; any chunk size; passes audio before start and after stop; stays under
   `SafeAudioFilter`'s 10 ms per-frame budget, so it is never switched off for being slow.
3. **Exit test, a call through Dograh's pipeline:** Dograh's own test harness
   (`api/tests/pipecat_test_utils.py`) runs a call pipeline with a test transport and stubbed
   speech-to-text and LLM, the agent configured with `noise_reduction: {enabled: true, engine:
   "nexora"}`. Noisy speech goes in; the test checks that the audio reaching speech
   recognition is the nexora-audio output (noise removed, speech kept), that `SafeAudioFilter`
   never tripped, and that the call ends normally.
4. **Telemetry off** with NEXORA's settings (2).

Not in P0: a real phone call through a telephony provider (needs provider accounts) and a full
Docker Compose stack in CI (the image build is checked; running it with Postgres, Redis and a
model key comes in P2).

## 5. CI

A new workflow, `.github/workflows/platform.yml`, on changes to `platform/**` or `nexora-audio/**`:
build the nexora-audio wheel → `fetch.sh` (clone pinned Dograh + Pipecat, apply patches) →
install Dograh's API dependencies and the wheel → run tests 1-4. A second job builds Dograh's
API Docker image with the patches to prove it still builds.

## 6. Also in P0 (documents, after the code)

- **Specs for P1 (NEXORA Core) and the Workflow Runner**, for your approval before P1.
- **Licence enquiry to LangGenius (Dify):** I draft it; you decide whether to send it.

## Risks

- **Dograh's Pipecat fork vs nexora-audio's Pipecat integration:** the filter API
  (`BaseAudioFilter`) is the same, but the fork may differ; test 2 catches it.
- **Time budget:** DeepFilterNet runs at 48 kHz, so telephony audio is resampled; if a 20 ms
  frame costs more than 10 ms on CI machines, `SafeAudioFilter` switches it off. Test 2
  measures this; the fallback is `noise_backend="rnnoise"` inside nexora-audio.
- **Dograh's install size:** its full dependency set is large; CI installs only what the API
  tests need.

## Decisions for you

None block P0. Two notes:

- New agents created through NEXORA will have `nexora` noise removal on (from P2). Say if you
  want it off by default.
- The plan's five open questions (licence enquiry, SaaS vs enterprise first, first industry,
  team size, data region) are still open; they matter from P1 on.
