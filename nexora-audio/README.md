# nexora-audio

Real-time audio processing SDK for Python: noise cancellation, voice activity
detection, gain control and streaming for voice agents, WebRTC, call-center
and meeting applications.

> **Status: 0.1.0.dev0 — Phase 3 of 9.** The configuration, capability
> reporting and streaming pipeline core are implemented and tested. **No audio
> backend ships yet**, so `initialize()` currently raises
> `FeatureUnavailableError` for every feature. Noise cancellation (RNNoise)
> arrives in Phase 5. See `docs/PHASE1_TECHNICAL_PLAN.md`.

## Install (local, not published)

```bash
pip install -e ".[dev]"          # from this folder
pip install -e ".[devices]"      # adds microphone/speaker support (needs PortAudio)
```

Requires Python 3.11+.

## What works today

```python
from nexora_audio import NexoraAudio, FeatureUnavailableError

audio = NexoraAudio(noise_cancellation=True, sample_rate=48000)

for feature, status in audio.capabilities().items():
    print(feature, status.available, status.backend, status.reason)

try:
    audio.initialize()
except FeatureUnavailableError as err:
    print(err)  # the SDK refuses to pretend to process audio
```

## Design principles
- **Honest capabilities**: a feature without a working backend raises
  `FeatureUnavailableError` and never passes audio through silently.
- **Any chunk size, any supported rate**: the pipeline reframes and resamples
  between the I/O format and each backend's native format, statefully, so
  chunked and whole-stream processing give the same result.
- **Measured latency**: `audio.latency` reports algorithmic and buffering delay.
  Tests check the reported value against a measured impulse delay.
- **Model-independent API**: backends plug in through a registry, so the
  public API stays the same when backends move to a native/Rust engine.

## Planned API (later phases)
`start_microphone()`, `get_processed_stream()`, `stop_microphone()`,
`process_chunk()`, `process_file()`. See the technical plan.

## Licences
Dependency and model licences: `docs/DEPENDENCY_LICENSES.md`.
The licence for nexora-audio itself has not been chosen yet.
