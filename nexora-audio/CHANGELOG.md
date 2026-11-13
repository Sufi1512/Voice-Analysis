# Changelog

## 0.1.0.dev0 — unreleased
### Fixed
- Speech cutting out in noisy audio: `noise_cancellation_strength` now defaults to 0.85
  (attenuation capped at ~16.5 dB). Speech dropouts went from 32–47% to 0–2% of frames.

### Added (voice enhancement)
- `voice_enhancement` (default on): 80 Hz high-pass, `clarity_db` presence EQ, -1 dBFS peak limiter.
- `auto_gain_control` (opt-in): slow, noise-floor-gated speech leveler.

### Added (Phase 5)
- RNNoise noise-cancellation backend (xiph RNNoise v0.2, built from the official
  release, bundled for Linux x86_64; `NEXORA_RNNOISE_LIBRARY` override; system-library fallback).
- `NexoraAudio.process_chunk()`, `flush()`, `reset()`, `backends`, `timing`.
- `NexoraAudio.process_file()` streaming file processing with latency-aligned output
  and `ProcessingReport`.
- `strength` blending, per-channel state for stereo.
- Public-domain speech fixture and seeded noise generators. Integration tests for
  quality, latency, chunking invariance and file I/O.

### Added (Phase 3)
- `NexoraConfig`: validated, immutable configuration (rates, channels, frame size, features).
- `NexoraAudio`: client with `capabilities()`, `initialize()`, `latency`, `close()` and context manager.
- Backend registry with availability probes and priority-based fallback.
- Core pipeline: `Processor` contract, `Reframer`, stateful `StreamingResampler`,
  `Pipeline` with analysis taps and latency reporting.
- Exception hierarchy rooted at `NexoraError`.
