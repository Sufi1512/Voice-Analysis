# NEXORA Voice Quality: Deep Analysis & Plan

**Status 2026-11-13:** E2a (quality lab) done. The first baseline found DeepFilterNet3 cutting
up to 78% of clean phone speech; fixed with the speech guard. Results and the current gate
status: `QUALITY_BASELINE.md`. Next: E2 (Dograh integration, loss concealment).

2026-11-13. Covers noise, echo, cutting, turn-taking and network problems in nexora-audio, Voice Cloud and the Dograh integration.

## Summary

No voice system can promise zero issues on every phone, room and network. What we can promise is that **no build ships unless it passes measured quality gates for noise, echo, cutting and turn-taking on realistic test audio, and every live call is monitored for the same problems.**

- **Where we are:** noise removal works well in pauses (background drops by 75 to 97 dB) with almost no speech cut (0 to 2.1%). But it has been tested on **one real speech clip with synthetic noise** only. Echo cancellation does not exist yet. Packet loss, clipping and level problems are not handled.
- **Biggest risks today:** the agent hearing its own voice (false interruptions), babble and nearby voices, 8 kHz phone audio, and choppy audio from network loss.
- **The plan:** first build a real test corpus and automated quality gates (E2a), then fix in order: Dograh integration with loss concealment (E2), noise and phone audio (E3), echo (E4), turn-taking (E5), nearby-voice removal (E11).
- **Quality bar:** the pass thresholds in "How we prove it". They are our targets, to be tuned once the corpus exists.

## Every way a call can sound bad

Thirteen distinct problems can make a call sound bad; today nexora-audio handles four well, six partly and three not at all.

| # | Problem | What the person hears | Main cause | Today | Fixed in |
| --- | --- | --- | --- | --- | --- |
| F1 | Steady background noise | Fan, traffic, hum behind the voice | Caller's environment | Handled: pauses -75 to -97 dB; under the voice only 10 to 17 dB less | E3 (under-voice) |
| F2 | Noise pumping | Noise switching on and off between words | Suppression gain jumping between speech and pause | Handled: speech-gated DFN3 | Keep in gates |
| F3 | Speech cutting / dropouts | Syllables or word endings missing | Over-suppression, VAD missing quiet speech | Handled: 0 to 2.1% audible speech cut | Keep in gates |
| F4 | Babble and nearby voices | Other people talking behind the caller | Call centres, cafes, TV | Partly: treated as noise, often kept as speech | E3, E11 |
| F5 | Narrowband phone audio | Muffled, robotic after cleaning | 8 kHz G.711 calls; models trained on wideband | Partly: works, not tuned or tested on real calls | E3 |
| F6 | Acoustic echo | Agent's own voice coming back | Speakerphone, laptop speakers, cheap headsets | **Not handled** | E4 |
| F7 | Line echo | Delayed copy of the agent | Phone network hybrids, some SIP gateways | **Not handled** | E4 |
| F8 | False barge-in | Agent stops talking for no reason | Echo, noise or a cough taken as the caller speaking | Partly: rule-based, no echo awareness | E4, E5 |
| F9 | Turn-taking errors | Caller cut off mid-thought, or long silences | Silence-only end-of-turn (700 ms fixed) | Partly | E5 |
| F10 | Choppy audio | Gaps, clicks, robotic bursts | Packet loss and jitter | **Not handled** (no loss concealment) | E2 |
| F11 | Wrong level | Too quiet or too loud | Mic gain, distance | Partly: AGC exists but is off by default | E3 |
| F12 | Clipping | Harsh distortion on loud speech | Input already clipped, or our gain | Partly: output limiter only; clipped input not detected | E3 |
| F13 | Added delay | Slow, awkward conversation | Processing latency stacking | Handled: 30 ms DFN3, measured | Keep in gates |

## Where nexora-audio stands today

The pipeline is fast and clean in pauses, but its evidence is thin: one public-domain speech clip (JFK, 16 kHz) mixed with synthetic white, pink and keyboard-like noise.

**Measured** (default chain: DeepFilterNet3 gated by Silero VAD, plus voice enhancer; JFK clip with 2 s noise-only padding; source: `PHASE1_TECHNICAL_PLAN.md` §9):

| Noise | Pauses vs input noise | Noise under the voice | STOI after | Audible speech cut |
| --- | --- | --- | --- | --- |
| pink 10 dB | -75.2 dB | -17.1 dB | 0.757 | 2.1% |
| white 10 dB | -79.1 dB | -15.0 dB | 0.750 | 1.4% |
| pink 0 dB | -87.7 dB | -12.5 dB | 0.647 | 0.6% |
| white 0 dB | -96.5 dB | -10.6 dB | 0.633 | 0.0% |

**Speed:** 30 ms algorithmic delay; p99 under 6 ms per 20 ms chunk; about 5.6 calls per CPU core (DFN3) or 14.7 (RNNoise) (`benchmarks.md`).

**What the code has but does not finish:**

- `echo_cancellation=True` raises `FeatureUnavailableError`: the interface with a `reference=` stream exists, the engine does not.
- Turn events are rule-based on Silero VAD: end of turn after 700 ms of silence, interruption after 400 ms of speech while the agent talks. The tracker knows *that* the agent is speaking but not *what* it said, so echo of the agent counts as the caller.
- Auto gain control exists but is off by default, because even the slow version cost about 0.015 STOI.
- Codecs: PCM16, float32, G.711 μ-law and A-law (bit-exact). No Opus, no packet-loss concealment.
- Binaries: Linux x86-64 only; DFN3 needs glibc 2.35.

**Untested, so unknown:** real phone recordings, babble, music, reverberant rooms, real devices, children's and elderly voices, Arabic and other languages, long calls (drift, memory), echo of any kind.

## Target audio pipeline

Every stage runs in this order; the agent's outgoing audio is tapped after encoding to become the echo reference.

**Caller → AI (inbound):**

1. Network in: decode codec (G.711, Opus); detect gaps by sequence/timestamp.
2. Loss concealment: fill missing frames (never raw zeros).
3. Input monitors: level, clipping, hum, estimated SNR.
4. Resample to the processing rate (integer ratios, compiled FIR).
5. **Echo canceller** (WebRTC AEC3) with the agent reference (E4).
6. **Noise removal**: DFN3 with adaptive strength, speech-gated by Silero VAD (E3).
7. Voice enhancer: 80 Hz high-pass, clarity EQ, hum notch when detected, AGC only for quiet calls, limiter.
8. VAD + turn detector + echo-aware barge-in (E4.3, E5) → events to the agent.
9. Clean audio → STT → AI.

**AI → caller (outbound):** TTS → encode → network out; the encoded-then-decoded copy feeds stage 5 as the reference.

**Per-call metrics** from every stage go to live monitoring (see "How we prove it").

## Noise

For an AI agent the main listener is the speech-to-text engine, not a person, so noise work is judged first by transcription accuracy and only then by how it sounds.

**Principle:** never make clean speech worse. Dograh's own benchmark found RNNoise hurts clean and lightly noisy speech; a cleaner that over-works turns a clean call into a robotic one.

**N1. Adaptive strength per call (fixes F1, protects clean calls)**

- Estimate the noise floor and SNR continuously from the pauses (Silero already marks them).
- Above about 30 dB SNR: light mode (pause gate only, no suppression under the voice).
- 10 to 30 dB: today's default (20 dB cap under speech, 40 dB pause gate).
- Below 10 dB: strong mode (higher cap, accepted only if it passes the speech-cut gate).
- Change modes slowly (seconds, with hysteresis) so the background never pumps (F2).

**N2. Babble and nearby voices (F4)**

- Background talkers are usually far from the microphone, so they arrive quieter and more reverberant than the caller.
- Track the main speaker's running level; treat speech-like energy well below it (starting point 12 dB, tuned on the corpus) as background and suppress it.
- This is a single-microphone heuristic, so it is a first step. The full fix is target-speaker extraction (E11): learn the caller's voice from the first seconds of the call and keep only that voice.

**N3. 8 kHz phone audio (F5)**

- Today 8 kHz audio is upsampled to 48 kHz for DFN3, which was trained on full-band speech. The empty top band may change how it behaves.
- Compare three paths on real G.711 calls: DFN3 on upsampled audio (today), RNNoise, and a DeepFilterNet model fine-tuned on narrowband speech (its training code is MIT/Apache).
- Keep the output at 8 kHz for telephony STT models. No bandwidth extension: it adds sound that the recognizer never trained on.

**N4. Noise under the voice (F1)**

- Today noise drops only 10 to 17 dB while someone talks. Raising DFN3's speech cap removes more noise but starts cutting quiet syllables.
- Make the cap follow the measured SNR (N1), and test each step against the speech-cut and transcription gates. Accept whichever setting the gates allow, nothing more.

**N5. Music, TV and hold music**

- Add music and TV to the test corpus. Music with vocals behaves like babble (N2); instrumental music should be removed by DFN3.

## Echo

Echo is the most damaging gap today: when the caller's device plays the agent's voice and the microphone picks it up, the agent hears itself, thinks the caller interrupted, and stops talking. We fix it in four layers, cheapest first.

**Where echo comes from, by path:**

| Path | Who cancels echo today | Risk |
| --- | --- | --- |
| Phone (PSTN, mobile) | The handset's own canceller; carriers usually cancel line echo | Low to medium: speakerphones and some SIP gateways leak |
| Browser (WebRTC) | The browser's canceller, if the app asks for it | Low if enabled, high if the app turns it off |
| BYO WebSocket (Voice Cloud) | Whatever the customer's app does, often nothing | **High** |
| Kiosks, cars, smart speakers | Device-dependent | High |

**E4.1 Make sure the caller's side cancels echo.** Our web SDK requests browser echo cancellation by default. Voice Cloud's docs and client SDK warn when it is off. Cheapest, and it fixes most browser calls.

**E4.2 Server-side echo cancellation with the agent's voice as reference.** We know exactly what the agent said, so we can subtract it.

- Engine: WebRTC AEC3 from the standalone `webrtc-audio-processing` library (BSD-3). Built and bundled like RNNoise and DFN3.
- The reference is the agent audio **as the caller received it**: after our codec encode and decode, so it matches what comes back.
- AEC3 estimates the echo delay itself. The phone path can add hundreds of milliseconds, so we must verify its delay range covers our paths, and log the estimated delay per call.
- It runs **before** noise removal. A noise model in front would change the echo and stop the canceller from matching it.
- Its residual-echo suppressor handles the non-linear part (small speakers distorting the sound).

**E4.3 Echo-aware barge-in.** Even good cancellers leave some residual echo.

- While the agent talks, compare the microphone signal with the delayed reference. If the energy patterns match, it is echo, not the caller.
- Raise the interruption threshold while the agent is speaking and residual echo is high. Lower it again when the measured echo is low.
- Double-talk (both speaking at once) must still interrupt: a real caller's voice does not match the reference.

**E4.4 Line echo.** The same canceller handles the linear echo some phone networks create. Its echo tail must cover the longest delay we measure on real trunks.

**Not done:** stereo or multi-microphone echo cancellation. All our inputs are mono.

## Cutting, dropouts, barge-in and turn-taking

"Cutting" means two different things with different fixes: audio removed by our processing (F3), and the caller cut off by the agent (F8, F9).

**C1. Processing never removes speech (F3).**

- The audible-speech-cut gate runs on every change (see "How we prove it").
- Hold speech protection for a short hangover after the VAD says speech ended, so word endings and soft consonants survive. Tune the hangover on the corpus.
- Use DFN3's lookahead so protection starts before a word's first syllable, not after it.

**C2. End of turn (F9, phase E5).**

- Today: 700 ms of silence ends a turn, for every sentence. Fast talkers wait too long; people who pause mid-thought get cut off.
- Add a learned end-of-turn model that judges from the audio whether the sentence sounds finished. Smart Turn is the first candidate; its licence and model download must be verified first.
- Combine it with the STT's own end-of-utterance signal where the provider gives one.
- Adaptive silence: short when the model says "finished", longer when it says "unfinished" ("and um…").

**C3. Barge-in (F8).** The caller interrupts the agent only when all hold:

- The speech does not match the agent's echo (E4.3).
- It lasts at least 400 ms (today's setting), or the STT confirms real words.
- It is not a backchannel ("yeah", "uh-huh"), which the agent keeps talking over (already reported as a separate event).
- Coughs, clicks and door slams are rejected: short non-speech bursts never count.

**C4. Languages.** Pauses, backchannels and sentence endings differ by language. The turn test set must include the languages NEXORA sells in first.

## Network and telephony

Audio that arrives damaged cannot be cleaned afterwards, so the input stage must handle loss, timing and level before any model sees it.

- **Gaps and packet loss (F10):** detect missing or late frames by sequence number or timestamp. Fill them with packet-loss concealment (G.711 Appendix I style for phone audio, Opus's built-in concealment for Opus) instead of raw silence. Raw zeros cause clicks and reset the VAD.
- **Opus support:** add Opus (BSD licence) for WebRTC and BYO WebSocket, with in-band forward error correction on.
- **Jitter:** the transport (telephony provider, WebRTC, Pipecat) owns the jitter buffer. Voice Cloud runs over TCP: no loss, but bursts. Pace processing by audio time, not arrival time.
- **Clock drift on long calls:** compare samples received with wall-clock time; resynchronise before the drift is audible.
- **Transcoding:** decode once, process once, encode once. Never μ-law → PCM → μ-law twice.
- **Level (F11):** measure input level per call. Turn on the slow leveller automatically only when the caller stays too quiet for several seconds (AGC costs about 0.015 STOI, so not on every call).
- **Clipping (F12):** count samples at full scale. Report clipped calls; reduce gain upstream where we control it (our web SDK). Repairing clipped audio is research, not planned.
- **Hum and DC:** the 80 Hz high-pass already removes DC and rumble. Add a 50/60 Hz hum notch only when hum is detected (mains is 60 Hz in Saudi Arabia, 50 Hz in Europe).

## How we prove it

Nothing ships on a single test clip again. Every claim about quality is measured on a corpus that looks like real calls, and a change that makes any gate worse is blocked.

**Test corpus v1 (built in E2a):**

| Set | Contents | Source |
| --- | --- | --- |
| Clean speech | Many speakers: male, female, young, old; English, Arabic and other launch languages | LibriSpeech (CC BY 4.0, verify), own recordings with consent |
| Noise | Stationary (fan, car, hum), street, office, call centre, babble, music, TV, keyboard | MUSAN (CC BY 4.0, verify), own recordings |
| Mixes | Speech + noise at -5, 0, 5, 10, 20, 30 dB SNR | Generated |
| Real phone calls | Our own test calls through each telephony provider, 8 kHz G.711 | Recorded by us |
| Echo | Agent TTS played through speakerphones, laptops, cheap headsets and recorded back; single-talk and double-talk | Own recordings; Microsoft AEC Challenge data if its licence allows |
| Turns | Conversations labelled with true end-of-turn and interruption moments | Own recordings, labelled |
| Network | The mixes with simulated 1, 3, 5 and 10% packet loss and bursty jitter | Generated |

**Quality gates (targets, to be tuned against the baseline):**

| Gate | Target |
| --- | --- |
| Audible speech cut | ≤ 2% on every mix at 0 dB SNR and above |
| Transcription accuracy (STT WER) | Clean speech: no worse than raw (≤ 0.5 points). Noisy speech at 5 dB SNR or below: at least 20% fewer errors than raw |
| Intelligibility (STOI) | Never below the input on any set (tolerance 0.01) |
| Noise in pauses | At least 60 dB below the input noise |
| Noise pumping | Pause level varies by ≤ 3 dB |
| Echo removed (ERLE) | ≥ 30 dB within 1 s of the agent starting to speak |
| False barge-in | ≤ 1 per 100 agent utterances; none on the echo-only set |
| Missed barge-in | ≤ 2% of real interruptions |
| Double-talk | Caller's speech cut ≤ 3% while the agent talks |
| Turn cut-off | ≤ 3% of turns ended while the caller had more to say |
| Reply gap | Median ≤ 800 ms from end of speech to end-of-turn event |
| Added delay | ≤ 40 ms with echo cancellation on; p99 processing ≤ 10 ms per 20 ms chunk |
| Packet loss 5% | No clicks; STOI drop ≤ 0.05 vs no loss |

PESQ and POLQA are not used: both are licensed ITU tools. A perceptual score (DNSMOS) is added only if its licence allows commercial use.

**Automation:**

- Every pull request that touches audio runs the fast gates (a subset of the corpus, a few minutes).
- Nightly: the full corpus, results stored and compared with the last release.
- A release needs all gates green and a written listening check of 20 clips by a person.

**Live monitoring, every call:** estimated SNR, pause noise level, speech-cut proxy, echo delay and ERLE, barge-ins and backchannels, clipping, concealed audio (ms), processing lag. Dashboards per customer and alerts when a call crosses a threshold. Recordings are kept for review only with the customer's consent and retention settings.

## Roadmap

Quality work runs in this order; each phase ends only when its gates pass on the corpus and nothing else got worse. Durations are estimates for one or two engineers.

| Phase | Work | Estimate | Gate to finish |
| --- | --- | --- | --- |
| E2a | Quality lab: corpus v1, metric suite, CI gates, baseline report of today's pipeline | 2 to 3 weeks | Baseline measured on every set |
| E2 | Dograh integration, live per-call metrics, gap concealment and Opus | 2 to 3 weeks | Real calls run through nexora-audio; loss gate passes |
| E3 | Noise and phone audio: N1 to N5, level, clipping, hum | 4 to 6 weeks | Noise, speech-cut, STT and STOI gates pass on all sets |
| E4 | Echo: E4.1 to E4.4 | 4 to 6 weeks | ERLE, false-barge-in and double-talk gates pass |
| E5 | Turn-taking: C2 and C3 | 3 to 4 weeks | Turn cut-off and reply-gap gates pass |
| E11 | Target-speaker extraction (nearby voices) | 4-week research spike | Go or no-go on the babble set |

## Risks and open questions

| Risk | Mitigation |
| --- | --- |
| Over-cleaning makes transcription worse | STT accuracy is a gate, not an afterthought |
| AEC3's delay range or non-linear handling falls short on phone paths | Measure on real trunks in E4 week 1; fall back to echo-aware barge-in (E4.3) |
| Reference mismatch: carriers transcode or process the agent's audio | Build the reference after our codec; measure the match per call |
| CPU: echo cancellation + DFN3 + VAD lowers calls per core below 5.6 | Benchmark each phase; RNNoise mode for high-density customers |
| Dataset and model licences (MUSAN, LibriSpeech, AEC Challenge, DNSMOS, Smart Turn) | Verify each before use; record in `THIRD_PARTY_NOTICES.md` |
| Recording real calls needs consent | Consent flow and retention settings before any recording |
| Single-microphone limits for babble | E11 research; set expectations with customers |

**Open questions for you:**

- [ ] Which languages and dialects come first (for example Gulf Arabic, English)?
- [ ] Which telephony providers do your first customers use?
- [ ] Can you provide real call recordings (with consent) for the corpus?
- [ ] Which speech-to-text providers do the agents use? The STT gate is measured with them.
- [ ] Is a GPU available for fine-tuning the narrowband model (N3)?
