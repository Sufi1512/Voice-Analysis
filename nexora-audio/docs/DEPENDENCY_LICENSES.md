# Phase 2 — Dependency and licence evaluation

Checked 2026-11-13 on Linux x86_64, Python 3.13.18 (`pip install --only-binary=:all:`
into a clean venv, licence fields read from installed package metadata and
bundled LICENSE files; upstream licences confirmed from project sources).
"Wheel" = installs on py3.13 without compiling.

## 1. Runtime dependencies

| Package | Version | Code licence | Bundled native / weights | Wheel py3.13 | Decision |
|---|---|---|---|---|---|
| numpy | 2.5.4 | BSD-3-Clause (+0BSD, MIT, Zlib parts) | — | ✅ | **Use** |
| scipy | 1.18.1 | BSD-3-Clause | — | ✅ | **Use** (resampling, filters) |
| pydantic | 2.14.3 | MIT | — | ✅ | **Use** (config) |
| onnxruntime | 1.31.1 | MIT | — | ✅ | **Use** (Silero, later DFN) |
| sounddevice | 0.5.6 | MIT | PortAudio bundled on Windows/macOS wheels; **Linux needs system `libportaudio2`** | ✅ | **Use**, optional extra `[devices]` |
| soundfile | 0.14.0 | BSD-3-Clause | Bundles **libsndfile (LGPL-2.1)**, loaded dynamically | ✅ | **Use** for WAV I/O; keep it a separate dynamic library (LGPL OK); add notice. Fallback: stdlib `wave` for 16-bit PCM |

## 2. Audio-processing backends

| Backend | Purpose | Code licence | Model-weight licence | Python packaging status | Measured (spike) | Decision |
|---|---|---|---|---|---|---|
| **RNNoise** (xiph) | Noise suppression, 48 kHz, 10 ms frames | BSD-3-Clause | BSD-3-Clause (default model ships in the library) | No official PyPI pkg. `pyrnnoise` 0.4.5 (Apache-2.0) bundles a prebuilt `librnnoise.so` but drags in matplotlib, audiolab, click, tqdm | ~0.6–0.9 ms per 10 ms frame (RTF ≈ 0.08); SNR −0.7 → 12.4 dB and 5.3 → 13.7 dB on synthetic signal | **In use (Phase 5).** Own `ctypes` binding; library built from the official xiph v0.2 release (not pyrnnoise), bundled for Linux x86_64 with notice + provenance |
| **WebRTC APM** via `webrtc-noise-gain` 1.3.0 | NS (levels 0–4) + AGC, 16 kHz int16, 10 ms only | Wrapper Apache-2.0; webrtc-audio-processing BSD-3-Clause | n/a (DSP) | ✅ wheel, tiny | 0.013 ms/frame; **degraded** our synthetic harmonic signal (SI-SDR 5.3 → −0.5 dB), ~125-sample delay | **Use for AGC.** NS kept as a fallback backend pending real-speech evaluation (synthetic tones are likely being estimated as stationary noise) |
| **Silero VAD** v6.2.3 | Voice activity detection, 8/16 kHz, 32 ms windows | MIT | MIT (ONNX files ship inside the wheel) | ✅ wheel, but package **hard-requires torch** | 0.11 ms per 32 ms window via onnxruntime alone; returned ~0 speech probability on synthetic tones (expected — not speech) | **Use**, via **onnxruntime directly** (no torch). Vendor `silero_vad.onnx` (2.3 MB) with MIT notice |
| **DeepFilterNet 3** | Neural enhancement, 48 kHz full-band | MIT OR Apache-2.0 | MIT OR Apache-2.0 (same repo) | `deepfilternet` 0.5.6 needs torch, pins **numpy<2**, and `deepfilterlib` has **no py3.13 wheel** | not run | **Defer to Phase 7** as optional "enhanced" backend using third-party ONNX exports (verify provenance) + our own STFT/ERB DSP, or the Rust libDF. ~2 frames lookahead → adds ≈20 ms latency |
| WebRTC AEC (`webrtc-audio-processing` 0.1.3) | Echo cancellation | BSD-3-Clause | n/a | **No wheel** for py3.13; stale | — | Not usable now |
| `speexdsp` 0.1.1 | AEC / NS | BSD (speex) | n/a | **No wheel** | — | Not usable now |
| `pyaec` 1.0.1 | AEC | **No licence declared** in metadata | n/a | wheel | — | **Excluded** (unclear licence) |

## 3. Test / evaluation dependencies

| Package | Licence | Status | Decision |
|---|---|---|---|
| pytest, ruff, mypy | MIT | ✅ | Use (dev extra) |
| pystoi 0.4.1 | MIT | ✅ wheel | Use for STOI |
| pesq 0.0.4 | Wrapper MIT; wraps ITU-T P.862 reference code whose own licensing terms are not established here | **No wheel** | **Excluded** for now (unclear licence + needs compiler) |

## 4. Test audio
Synthetic signals cannot validate VAD or neural NC (shown by the spike).
Candidate real-speech/noise fixtures — **licences to verify before download**:
LibriSpeech (speech), MUSAN or DEMAND (noise), or user-recorded clips with consent.

## 5. Attribution file
Ship `THIRD_PARTY_NOTICES.md` in the wheel containing: RNNoise BSD-3 notice,
Silero MIT notice, WebRTC BSD-3 + PATENTS, webrtc-noise-gain Apache-2.0,
libsndfile LGPL-2.1 notice (via soundfile), PortAudio notice (via sounddevice).
