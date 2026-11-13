# Changelog

## 0.1.0.dev0 — unreleased
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
