# Nexora Audio SDK (Python) — Phase 1 technical plan

**Status:** approved 2026-11-13 with defaults: Q1 vendor prebuilt RNNoise, Q2 download licensed fixtures after licence check, Q3 stay in Voice-Analysis, Q4 Python 3.11–3.13.
**Progress:** Phase 3 ✅ (2026-11-13). Next: Phase 4 (devices).
**Inputs:** Nexora implementation prompt; Krisp findings in
`../../investigation/03-developer-platform/DEVELOPER_PLATFORM.md`; Phase 2 results in
`DEPENDENCY_LICENSES.md`; spike in `../spikes/feasibility_spike.py`.

## 1. Repository inspection
- Repo `Sufi1512/Voice-Analysis` holds the Krisp investigation; no existing
  audio code. The SDK lives in `nexora-audio/` here until a dedicated
  `nexora-audio-sdk` repo exists. It is self-contained, so it can be moved with history.
- Build env: Python 3.13, 2 vCPU x86_64, **no audio devices and no PortAudio**
  in this workspace. Microphone tests must run on your machine; CI uses
  file/stream tests only.
- `nexora-audio` is free on PyPI (not published, per the prompt).

## 2. Architecture

### 2.1 Layers
```mermaid
flowchart TB
  subgraph Public API
    C[NexoraAudio client<br/>initialize · start_microphone · get_processed_stream<br/>process_chunk · process_file · capabilities · close]
  end
  C --> CFG[NexoraConfig (pydantic)]
  C --> ENG[Engine: lifecycle + threads + metrics]
  ENG --> P[Pipeline: ordered Processors + reframing/resampling adapters]
  P --> NC[NoiseCancellation] --> AGC[GainControl] --> VAD[VAD (analysis tap)]
  NC -. backend .-> RN[RNNoise ctypes]
  NC -. backend .-> WN[WebRTC NS]
  NC -. backend, Phase 7 .-> DF[DeepFilterNet ONNX]
  AGC -. backend .-> WA[WebRTC AGC]
  VAD -. backend .-> SV[Silero ONNX]
  ENG --> DEV[devices: Microphone / Playback / DeviceManager (sounddevice)]
  ENG --> IO[io: WAV reader/writer (soundfile, streaming blocks)]
```

### 2.2 Core contracts (model-independent, so they can be ported to Rust/JS later)
- **`AudioFrame`**: `float32` ndarray `(channels, samples)`, sample rate, monotonic
  sample index. Float32 [-1, 1] is the only internal format; int16 only at backend edges.
- **`Processor` protocol**: `native_rate`, `native_frame` (samples),
  `channels_supported`, `latency_samples`, `reset()`, `process(frame) -> frame`.
  Analysis processors (VAD) return events instead of audio.
- **Pipeline adapters**: each processor declares its native rate/frame, and the
  pipeline inserts a stateful `Reframer` (ring buffer) and polyphase `Resampler`
  between stages. Backends differ: RNNoise 48 kHz/480, WebRTC 16 kHz/160,
  Silero 16 kHz/512. Pipeline latency = sum of reported latencies + reframing delay,
  and `pipeline.latency_ms` exposes it.
- **Multichannel**: one backend state per channel. Stereo is processed per
  channel; VAD runs on a mono downmix.
- **Capabilities**: `NexoraAudio.capabilities()` returns per-feature
  `{available, backend, reason}`. If a requested feature has no working backend,
  `initialize()` raises `FeatureUnavailableError`. Nothing silently passes audio through.

### 2.3 Real-time threading
```
PortAudio callback ──copy──▶ input SPSC ring buffer ──▶ worker thread: pipeline.process()
       ▲ (no allocation, no inference, no locks)                    │
       └────────────── output ring (playback, optional) ◀───────────┴──▶ bounded queue ──▶ get_processed_stream() iterator
```
- The callback only copies memory. All inference runs on the worker thread.
- If the consumer stops reading and the bounded output queue fills, drop the
  oldest chunks and count them as `dropouts`. This is configurable.
- Device errors and disconnects are reported through a callback, followed by a
  bounded reconnect with backoff, and a `DeviceDisconnectedError` if that fails.

### 2.4 Public API mapping to the prompt
| Prompt API | Plan |
|---|---|
| `NexoraAudio(noise_cancellation=…, voice_isolation=…, echo_cancellation=…, auto_gain_control=…, sample_rate=…)` | Same kwargs, validated into `NexoraConfig`; plus `backend=`, `frame_ms=`, `channels=`, `device=` |
| `initialize()` | Loads backends, runs a warm-up frame, raises on unavailable features |
| `start_microphone()` / `stop_microphone()` / `get_processed_stream()` | As specified; iterator yields `AudioChunk(audio, sample_rate, t_start, vad_prob, speech_event)` |
| `process_chunk(chunk)` | Stateful; any chunk length (internally reframed); returns the processed samples available so far plus `flush()` |
| `process_file(input_path, output_path)` | Streams in blocks (never loads the whole file); returns `ProcessingReport` (duration, RTF, latency stats, VAD segments) |
| `voice_isolation=True` | **v0.1 raises `FeatureUnavailableError`.** No permissively licensed model reviewed here removes competing speakers. See risk R3 |
| `echo_cancellation=True` | **v0.1 raises `FeatureUnavailableError`.** The interface (with `reference=` playback stream) ships, but there is no usable backend (Phase 2) |

### 2.5 Package layout (adjusted from the prompt)
The prompt's tree is kept, with these changes:
- `backends/webrtc.py` and `backends/silero.py` added. `backends/deepfilternet.py` arrives in Phase 7.
- `core/reframer.py` and `core/resampler.py` added (needed because backend frame/rate contracts differ).
- `io/wav.py` replaces file handling scattered in `utils/`.
- `_vendor/models/silero_vad.onnx` + `THIRD_PARTY_NOTICES.md`.
- Optional extras: `[devices]` (sounddevice), `[eval]` (pystoi), `[dev]`.

## 3. Implementation plan (remaining phases)
| Phase | Deliverable | Done when (tests) |
|---|---|---|
| 3 ✅ | `pyproject` (hatchling, src layout), config, exceptions, `Processor`/`AudioFrame`, Reframer, Resampler, Pipeline, capabilities | Unit: config validation, reframer round-trip for 10/20/32/40 ms chunks, resampler 16↔48 kHz SNR > 60 dB on sine, pipeline latency arithmetic |
| 4 | devices: enumerate, select, capture + playback via sounddevice; SPSC ring buffer | Unit: ring buffer under concurrent producer/consumer. Device test **skipped without PortAudio**, run on your machine |
| 5 | RNNoise backend (ctypes), NoiseCancellation processor, `process_chunk`, `process_file` | Integration: WAV in → WAV out, sample count preserved (minus reported latency), SNR gain > 5 dB at 0 dB input SNR on fixtures; no allocations per frame in hot path |
| 6 | Engine worker thread, `start_microphone`, `get_processed_stream`, dropout accounting | Integration: simulated device feeding the engine at real-time pace for 60 s → 0 dropouts at 10 ms frames |
| 7 | Silero VAD (events: speech_start/speech_end with hysteresis, min durations), WebRTC AGC, WebRTC NS fallback; DeepFilterNet ONNX evaluated | VAD F1 on labelled real-speech fixture; AGC holds level within ±3 dB without clipping |
| 8 | Benchmarks (10/20/40 ms chunks, 16/48 kHz; per-chunk p50/p99, RTF, CPU, RSS, dropouts), audio-quality tests (SNR, SI-SDR, STOI), docs | `docs/benchmarks.md` generated by a script, with machine details |
| 9 | Build sdist + wheel, install into a clean venv, run examples | `pip install dist/*.whl` and quickstart run green |

## 4. Risks and limitations
| # | Risk | Mitigation |
|---|---|---|
| R1 | RNNoise binary distribution: pyrnnoise is heavy; building librnnoise downloads model data from xiph servers (likely blocked here) | Q1 below. Long-term: build in CI with cibuildwheel per OS |
| R2 | No audio hardware in this workspace, so mic acceptance (criterion 2) can't be proven here | You run `examples/microphone_noise_cancellation.py` locally, and I add a self-test command that logs device info and timing |
| R3 | **Voice isolation** (removing other speakers, Krisp's headline feature) has no permissive off-the-shelf model in this review | Ship honest `FeatureUnavailableError`; later options: personalized enhancement with a speaker embedding, or licensing Krisp VIVA (see Module 4 doc) |
| R4 | No AEC backend installable on py3.13 | Interface only in v0.1. Build WebRTC AEC3 (BSD-3) as part of the future native/Rust engine |
| R5 | Synthetic signals mislead (spike: Silero ≈ 0 on tones; WebRTC NS degraded tones) | Real speech + noise fixtures with verified licences (Q2) |
| R6 | Python GIL / jitter at 10 ms frames | Worker thread + ring buffers; native backends release the GIL in ctypes calls; measure p99 rather than mean |
| R7 | DeepFilterNet packaging incompatible with numpy 2 / py3.13 | ONNX route or Rust libDF in Phase 7. Optional, not on the critical path |
| R8 | Latency stacking (resampling + WebRTC ~7.8 ms + DFN lookahead) | Prefer 48 kHz end to end with RNNoise. Report `latency_ms` and test that it matches the measured value |

## 5. Spike results (evidence, not claims of final performance)
Synthetic harmonic "speech" + white noise, 2 vCPU, Python 3.13:
| Backend | Input SNR → output | Cost per frame |
|---|---|---|
| RNNoise 48 kHz/10 ms | 13.3 → 14.4 dB · 5.3 → 13.7 dB · −0.7 → 12.4 dB | median 0.6–0.9 ms, p99 ≤ 2.0 ms |
| WebRTC NS 16 kHz/10 ms (level 4) | SI-SDR 5.3 → −0.5 dB (degraded) | 0.013 ms |
| Silero VAD ONNX 16 kHz/32 ms | p(speech) ≈ 0.02 on tones (not speech) | 0.11 ms |

## 6. Open questions for you
- **Q1 RNNoise binary:** for v0.1, (a) depend on `pyrnnoise` only for its prebuilt `librnnoise` (heavy extra deps), (b) vendor the prebuilt BSD-3 library per platform in our package, or (c) build from xiph source in CI (needs network access to xiph model files)?
- **Q2 Test audio:** may I download a CC-licensed speech/noise set (e.g. LibriSpeech + MUSAN, licences verified first), or will you provide recordings?
- **Q3 Location:** keep `nexora-audio/` inside Voice-Analysis, or create a separate `nexora-audio-sdk` repo?
- **Q4 Python floor:** prompt says 3.11+. I'll test 3.11–3.13 unless you want otherwise.
