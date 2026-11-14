# E2 spec: real calls, lost packets, Opus and per-call quality

Phase E2 of `VOICE_QUALITY_PLAN.md`. Approved by the user on 2026-11-13 ("start implement
this plan"; "Yes" to starting E2). Gate: `loss_5pct` (STOI drop ≤ 0.05 at 5% loss) plus
no regression on any other gate.

## 1. Packet-loss concealment (F10)

Lost audio today reaches the noise model as digital silence: clicks, broken words, the
speech detector resetting (baseline: up to 0.09 STOI lost at 5% loss, 0.14 at 10%).

- New `streaming/plc.py`: waveform-substitution concealment in the style of ITU-T G.711
  Appendix I. On a lost 10 ms block: estimate the pitch period from the last 30 ms
  (66–400 Hz), repeat the last periods with a short overlap-add, keep full level for the
  first 10 ms, fade by 20% per further 10 ms, silent after 60 ms. On recovery, crossfade
  into the real audio.
- Two ways a loss is known:
  1. **Detected:** a 10 ms block of exact digital zeros right after audible signal (what
     jitter buffers and gateways insert for missing packets). Concealment stops after 60 ms,
     so real mutes are unaffected beyond a 60 ms fade.
  2. **Signalled:** `StreamSession.conceal(ms)` when the transport knows audio is missing
     and did not insert anything. Returns processed audio for that span, keeping time aligned.
- On by default for mono sessions (`loss_concealment=True`); per-session stats count it.

## 2. Opus input

- `AudioFormat(encoding="opus", sample_rate=8000|12000|16000|24000|48000)` for input. Each
  `process()` call carries exactly one Opus packet (one WebSocket message). An empty
  payload means a lost packet: the decoder's own concealment fills it. (In-band FEC would
  need a one-packet delay; not done, as our WebSocket transport does not lose packets.)
- Output stays PCM16, float32 or G.711 (output Opus would need packet framing; not needed
  for the agent side).
- Library: the system `libopus` (BSD-3), loaded over ctypes like our other native
  libraries; `NEXORA_OPUS_LIBRARY` overrides the path. Reported as a capability; a clear
  error if missing.

## 3. Per-call quality numbers

`StreamSession.quality()` returns, at any time: input speech level (dBFS), noise floor
(dBFS), estimated SNR, share of time with speech, clipped samples (%), concealed audio
(ms and %), speech-guard restorations, processing p50/p99 per chunk, added delay.
nexora-server records them when a session ends (JSON log line and Prometheus
histograms), so every live call can be monitored for the problems the lab measures.

## 4. Dograh integration

- `nexora_audio.integrations.pipecat.NexoraAudioFilter`: a Pipecat `BaseAudioFilter`
  (tested with Pipecat 1.16). One `StreamSession` per call, PCM16 at the transport rate,
  no turn events (Dograh has its own). Handles `FilterEnableFrame`, runs processing in a
  worker thread so the event loop stays free, logs `quality()` at stop. Extra:
  `pip install nexora-audio[pipecat]`.
- `integrations/dograh/`: a patch for the user's Dograh fork (we cannot push to it) that adds
  engine `"nexora"` to `services/pipecat/noise_reduction/factory.py`, the schema `Literal`
  and the workflow settings UI (engine selector), kept inside Dograh's fail-open
  `SafeAudioFilter`. Plus install steps.

## Acceptance

1. Lab `loss` set: worst STOI drop at 5% loss ≤ 0.05; all other gates no worse than baseline.
2. Unit tests: concealment level and fade, detection rules (no concealment of real silence
   or of the start of a stream), `conceal()` keeps output length aligned; Opus round trip
   with a lost packet; quality numbers on known signals; the Pipecat filter on real Pipecat
   classes (start, filter, enable/disable, stop) with output pacing equal to input.
3. The Dograh patch applies cleanly to the fork at `d672de29`.
