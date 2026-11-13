# Dograh integration: the `nexora` noise engine

This patch adds nexora-audio to Dograh as a second noise-reduction engine, next to RNNoise.
It is kept as a patch because the Dograh fork (`Sufi1512/dograh`) is a separate repository.

What it changes (5 files, +71/−3), against Dograh commit `d672de29`:

| File | Change |
| --- | --- |
| `api/services/pipecat/noise_reduction/factory.py` | Engine `"nexora"` → `NexoraAudioFilter`, settings from `NEXORA_AUDIO_SETTINGS` (JSON). If nexora-audio is missing or misconfigured, the call falls back to RNNoise instead of failing. Still wrapped in Dograh's fail-open `SafeAudioFilter` (10 ms per-frame budget). |
| `api/schemas/workflow_configurations.py` | `engine: Literal["rnnoise", "nexora"]` |
| `ui/src/client/types.gen.ts` | Same union in the generated client type |
| `ui/src/app/workflow/[workflowId]/settings/WorkflowSettingsSections.tsx` | Engine selector under "Reduce Background Noise" |
| `api/tests/test_noise_reduction.py` | Fallback test, and a test that the nexora engine cleans noise and keeps pace at 8 kHz |

## Apply and install

```bash
cd dograh                      # your fork, at or near d672de29
git apply /path/to/Voice-Analysis/integrations/dograh/0001-nexora-noise-engine.patch

# In Dograh's API environment. Do NOT use the [pipecat] extra: Dograh ships its own
# Pipecat fork, and the extra would install Pipecat from PyPI over it.
pip install "nexora-audio @ git+https://github.com/Sufi1512/Voice-Analysis#subdirectory=nexora-audio"
```

For the Docker image, add the same `pip install` line to `api/Dockerfile` after the other
requirements. nexora-audio bundles its Linux x86-64 native libraries (DeepFilterNet3 needs
glibc 2.35+, as in Ubuntu 22.04 / Debian 12 images).

Optional engine settings for every call (any nexora-audio setting):

```bash
NEXORA_AUDIO_SETTINGS='{"noise_backend": "rnnoise"}'   # higher call density, lighter cleaning
```

Then in a workflow: Settings → Noise Reduction → Reduce Background Noise → Engine: NEXORA.

## Verified

- Patch applies cleanly to `d672de29` (`git apply --check`).
- Dograh's `api/tests/test_noise_reduction.py` with the patch: 31 passed, 3 failed. The same 3
  fail without the patch: they need `pipecat/scripts/provider-watch/assets/speech-16k.wav` from
  the Pipecat submodule, which was not checked out here. Run with Pipecat 1.16 from PyPI and
  dummy `DATABASE_URL`/`REDIS_URL`, not Dograh's Pipecat fork: run the suite once in your own
  environment to confirm.
- At 8 kHz the nexora engine took 1.6 ms on average per 20 ms frame (max 4.6 ms), inside
  Dograh's 10 ms budget.

## What each call gets

DeepFilterNet3 noise removal with the speech guard (no more cutting of phone speech),
packet-loss concealment for gaps that arrive as silence, and the voice enhancer. At the end
of every call the filter logs its quality numbers (SNR, noise floor, clipping, concealed
audio, processing time) as `nexora-audio call quality`.
