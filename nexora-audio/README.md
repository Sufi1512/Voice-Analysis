# nexora-audio

Real-time audio processing SDK for Python: noise cancellation, voice activity
detection, gain control and streaming for voice agents, WebRTC, call-center
and meeting applications.

> **Status: 0.1.0.dev0.** Built for servers that sit between a WebSocket and an AI
> agent: per-call streaming sessions with noise cancellation (DeepFilterNet3, RNNoise
> fallback), clean pauses, voice enhancement, VAD, and turn/interruption events, over
> PCM16 or G.711 telephony audio. Microphone capture is not implemented (not needed server-side).
> See `docs/PHASE1_TECHNICAL_PLAN.md`.

## Install (local, not published)

```bash
pip install -e ".[io]"       # from this folder; [io] adds WAV/FLAC file support
pip install -e ".[dev]"      # tests, ruff, mypy
```

Python 3.11+. Native libraries are bundled for **Linux x86_64** only:
DeepFilterNet3 needs glibc 2.35+ (Ubuntu 22.04+), RNNoise runs on almost any Linux.
`NexoraAudio().capabilities()` shows which backend is used. On other platforms set
`NEXORA_DEEPFILTER_LIBRARY` and/or `NEXORA_RNNOISE_LIBRARY` (see
`src/nexora_audio/_native/PROVENANCE.md`).

## Use it between your WebSocket and your AI agent (server)

One `StreamSession` per caller. Feed raw bytes as they arrive. You get cleaned bytes
plus conversation events for your agent.

```python
from nexora_audio import AudioFormat, StreamSession

session = StreamSession(input_format=AudioFormat("pcm16", 16000))  # or ("mulaw", 8000)


async def on_client_audio(chunk: bytes) -> None:
    out = await session.aprocess(chunk)  # runs off the event loop
    await agent.send_audio(out.audio)  # cleaned audio, same format
    for event in out.events:  # speech_start, speech_end, end_of_turn,
        await agent.send_event(event.to_dict())  # interruption, backchannel


def on_agent_tts(playing: bool) -> None:
    session.set_agent_speaking(playing)  # enables interruption/backchannel events
```

| Event | Meaning | Typical agent action |
|---|---|---|
| `speech_start` | user started talking | optional: lower TTS volume |
| `speech_end` | user stopped (300 ms silence) | |
| `end_of_turn` | user finished their turn (700 ms silence after at least 200 ms of speech) | send the transcript to the LLM |
| `interruption` | user talked over the agent for 400 ms or more | stop TTS now |
| `backchannel` | short "uh-huh"/"yeah" while the agent talks | keep talking |

Turn and interruption detection is **rule-based** (Silero VAD plus timing, tunable via
`TurnConfig`). It doesn't understand words, so it can't tell an unfinished sentence from
a finished one, or a short "stop!" from a short "yeah".

A complete reference bridge (client WS -> nexora -> agent WS, with JSON events and
automatic agent-speaking detection) is in `nexora_audio.integrations.websocket_bridge`:

```bash
pip install -e ".[server]"
python examples/websocket_bridge.py --agent ws://localhost:9000/agent --port 8765
```

**Formats:** `pcm16`, `float32`, `mulaw`, `alaw` (G.711, bit-exact with the ITU reference),
8-48 kHz, mono or stereo. The input and output formats can differ (e.g. 8 kHz in, 16 kHz out).
**Capacity:** about 4 concurrent calls per CPU core with the default pipeline, about 10 with
RNNoise (`docs/benchmarks.md`). Sessions run in parallel across cores.
**Latency:** about 32 ms at 16 kHz with the default pipeline (`session.latency_ms`).

## Denoise a file

```python
from nexora_audio import NexoraAudio

audio = NexoraAudio(noise_cancellation=True)
audio.initialize()
result = audio.process_file(input_path="noisy_audio.wav", output_path="clean_audio.wav")
print(result.real_time_factor, result.backends)
audio.close()
```

Files are streamed in blocks at their own rate (mono or stereo). The output has
the same length, rate and sample format as the input, with the processing delay
removed so the two line up sample for sample.

## Denoise a stream

```python
with NexoraAudio(sample_rate=16000, frame_ms=10) as audio:
    for chunk in incoming_chunks():  # int16 or float32, 1-D or (samples, channels)
        clean = audio.process_chunk(chunk)  # same dtype and layout back
        send_to_stt(clean)
    send_to_stt(audio.flush())  # end of stream
```

- Chunks that are a multiple of `audio.config.frame_samples` come back at the same size.
- `audio.latency.algorithmic_ms` gives the added delay: 30 ms with DeepFilterNet3
  (20 ms with RNNoise), plus ~2 ms of resampling at 16 kHz.
- `audio.reset()` starts a new, unrelated stream.

## How the default processing works
1. **DeepFilterNet3** removes noise, including noise under the voice (RNNoise if DFN3
   can't load).
2. **Silero VAD** runs alongside. While someone speaks, suppression is capped
   (`deepfilter_speech_atten_lim_db`, 20 dB) so quiet word parts survive. In pauses there
   is no cap, plus a smooth extra gate (`pause_gate_db`, 40 dB), so pauses are silent.
   The model's own 30 ms delay lets the gate open before a word reaches the output.
3. **Speech guard** (`speech_guard=True`): in frames above the noise floor that may be
   speech, the model may never remove more than the noise can explain (+6 dB,
   `speech_guard_margin_db`). Without it DeepFilterNet3 cut up to 78% of clean 8 kHz phone
   speech; with it, at most 3.6% on the quality lab's phone set (`docs/QUALITY_BASELINE.md`).
4. **Voice enhancement**: 80 Hz high-pass, +3 dB clarity at 3 kHz (`clarity_db`),
   peak limiter at -1 dBFS.
5. **Gain control** (`auto_gain_control=True`, off by default): slow speech leveler.

| Setting | Default | Effect |
|---|---|---|
| `noise_backend` | `"auto"` | `"deepfilternet3"` or `"rnnoise"` to force one |
| `speech_protection` | `True` | Speech-gated caps/gate as above. `False` = constant suppression |
| `deepfilter_speech_atten_lim_db` | `20` | Max noise removal while speaking (higher = cleaner but riskier) |
| `pause_gate_db` | `40` | Extra attenuation in pauses |
| `speech_guard`, `speech_guard_margin_db` | `True`, `6` | Never remove speech beyond the noise share (see step 3) |
| `noise_cancellation_strength` / `speech_protection_strength` | `1.0` / `0.85` | Same idea for the RNNoise backend |
| `voice_enhancement`, `clarity_db` | `True`, `3.0` | High-pass + clarity EQ + limiter |
| `auto_gain_control` | `False` | Level speech towards `agc_target_dbfs` (-20) |
| `vad` | `False` | Report speech probability and start/end events via `audio.pop_results()` |

Measured results and how the defaults were chosen: `docs/PHASE1_TECHNICAL_PLAN.md`, sections 8 and 9.

## Check what runs on this machine

```python
for feature, s in NexoraAudio().capabilities().items():
    print(f"{feature:20} {s.available!s:5} {s.backend or '-':8} {s.reason}")
```

## Measured performance (preliminary, Phase 8 will formalise)
DeepFilterNet3: about 1.1 ms per 10 ms frame at 48 kHz (real-time factor ~0.12 per channel).
RNNoise backend (Intel Xeon 2.1 GHz, 2 vCPU, Python 3.13, `process_chunk` timing only):

| I/O rate | Chunk | p50 | p99 | Real-time factor | Added latency |
|---|---|---|---|---|---|
| 48 kHz | 10 ms | 0.09 ms | 0.13 ms | 0.009 | 20.0 ms |
| 48 kHz | 20 ms | 0.19 ms | 0.37 ms | 0.010 | 20.0 ms |
| 48 kHz | 40 ms | 0.38 ms | 1.05 ms | 0.010 | 20.0 ms |
| 16 kHz | 10 ms | 0.29 ms | 0.40 ms | 0.029 | 22.0 ms |

These are processing times, not end-to-end device latency (timed before voice
enhancement was added; the enhancer is a few IIR filters). Quality on a public-domain
speech clip with added noise is in the technical plan, section 8. Synthetic-noise
results are not proof of real-world quality.

## Examples
- `examples/process_audio_file.py noisy.wav clean.wav`
- `examples/streaming_chunks.py input.wav`: simulates a live stream of 10 ms chunks

## Design principles
- **Honest capabilities**: a feature without a working backend raises
  `FeatureUnavailableError` and never passes audio through silently.
- **Any chunk size, any rate**: the pipeline reframes and resamples statefully,
  so chunked and whole-stream processing give the same result (tested).
- **Measured latency**: the declared latency is checked against measured delay on real speech.
- **Model-independent API**: backends plug in through a registry.

## Licences
Bundled: DeepFilterNet3 (MIT OR Apache-2.0), RNNoise (BSD-3-Clause), Silero VAD model (MIT). See `src/nexora_audio/THIRD_PARTY_NOTICES.md`
and `src/nexora_audio/_native/PROVENANCE.md`. Dependency review:
`docs/DEPENDENCY_LICENSES.md`. The licence for nexora-audio itself has not been chosen yet.

## Quality lab
Every audio change is measured on a 242-case test corpus (noise, phone, reverb, echo, turns,
packet loss) against quality gates: `python -m qualitylab run --profile fast`. See
`docs/QUALITY_BASELINE.md` and `docs/VOICE_QUALITY_PLAN.md`.

## Live calls: lost packets, Opus, quality numbers, Pipecat/Dograh
- **Lost packets**: gaps that arrive as digital silence (what jitter buffers and gateways
  insert) are concealed G.711-Appendix-I style: pitch repetition, fading out over 60 ms.
  If the transport knows audio is missing, call `session.conceal(ms)`.
  `StreamSession(loss_concealment=False)` turns it off.
- **Opus input**: `AudioFormat("opus", 16000)`, one packet per `process()` call, `b""` for
  a lost packet. Output is PCM16 (or float32/G.711). Needs the system `libopus`
  (`apt install libopus0`).
- **Per-call quality**: `session.quality()` gives speech level, noise floor, SNR, clipping,
  concealed audio, speech-guard restorations, processing time and delay.
- **Pipecat / Dograh**: `nexora_audio.integrations.pipecat.NexoraAudioFilter` is a Pipecat
  audio input filter (`pip install "nexora-audio[pipecat]"`). For Dograh, see
  `../integrations/dograh/`.

