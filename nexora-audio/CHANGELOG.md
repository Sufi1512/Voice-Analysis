# Changelog

## 0.1.0.dev0 — unreleased
### Added (Phase 3)
- `NexoraConfig`: validated, immutable configuration (rates, channels, frame size, features).
- `NexoraAudio`: client with `capabilities()`, `initialize()`, `latency`, `close()` and context manager.
- Backend registry with availability probes and priority-based fallback.
- Core pipeline: `Processor` contract, `Reframer`, stateful `StreamingResampler`,
  `Pipeline` with analysis taps and latency reporting.
- Exception hierarchy rooted at `NexoraError`.
