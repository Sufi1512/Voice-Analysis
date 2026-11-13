# nexora-audio

Real-time audio processing SDK for Python: noise cancellation, voice activity
detection, gain control and streaming for voice agents, WebRTC, call-center
and meeting applications.

> **Status: 0.1.0.dev0, Phases 3 and 5 of 9 done.** Noise cancellation (RNNoise)
> works for streaming chunks and files. Microphone capture, VAD and gain control
> are not implemented yet. Asking for them raises `FeatureUnavailableError`.
> See `docs/PHASE1_TECHNICAL_PLAN.md`.

## Install (local, not published)

```bash
pip install -e ".[io]"       # from this folder; [io] adds WAV/FLAC file support
pip install -e ".[dev]"      # tests, ruff, mypy
```

Python 3.11+. The RNNoise library is bundled for **Linux x86_64**. On other
platforms, set `NEXORA_RNNOISE_LIBRARY` to a `librnnoise` built from
https://github.com/xiph/rnnoise, or install your OS package (`librnnoise0`).

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
    for chunk in incoming_chunks():          # int16 or float32, 1-D or (samples, channels)
        clean = audio.process_chunk(chunk)   # same dtype and layout back
        send_to_stt(clean)
    send_to_stt(audio.flush())               # end of stream
```

- Chunks that are a multiple of `audio.config.frame_samples` come back at the same size.
- `audio.latency.algorithmic_ms` gives the added delay: 20 ms at 48 kHz, 22 ms at 16 kHz
  (RNNoise plus resampling).
- `audio.reset()` starts a new, unrelated stream. `noise_cancellation_strength=` (0–1)
  blends in the original signal.

## Check what runs on this machine

```python
for feature, s in NexoraAudio().capabilities().items():
    print(f"{feature:20} {s.available!s:5} {s.backend or '-':8} {s.reason}")
```

## Measured performance (preliminary, Phase 8 will formalise)
Intel Xeon 2.1 GHz, 2 vCPU, Python 3.13, noisy speech, `process_chunk` timing only:

| I/O rate | Chunk | p50 | p99 | Real-time factor | Added latency |
|---|---|---|---|---|---|
| 48 kHz | 10 ms | 0.09 ms | 0.13 ms | 0.009 | 20.0 ms |
| 48 kHz | 20 ms | 0.19 ms | 0.37 ms | 0.010 | 20.0 ms |
| 48 kHz | 40 ms | 0.38 ms | 1.05 ms | 0.010 | 20.0 ms |
| 16 kHz | 10 ms | 0.29 ms | 0.40 ms | 0.029 | 22.0 ms |

These are processing times, not end-to-end device latency. Measured on a public-domain
speech clip with added white noise at 0 dB SNR: SI-SDR improved from 0 dB to about 13 dB.
Synthetic-noise results are not proof of real-world quality.

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
Bundled RNNoise is BSD-3-Clause. See `src/nexora_audio/THIRD_PARTY_NOTICES.md`
and `src/nexora_audio/_native/PROVENANCE.md`. Dependency review:
`docs/DEPENDENCY_LICENSES.md`. The licence for nexora-audio itself has not been chosen yet.
