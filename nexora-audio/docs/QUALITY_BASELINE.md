# Voice quality baseline (phase E2a), 2026-11-13

The quality lab (`nexora-audio/qualitylab/`) now measures nexora-audio on a 242-case corpus
(61 minutes of audio) and checks 17 quality gates from `VOICE_QUALITY_PLAN.md`. This page
records what the first measurement found, the fix it led to, and where the product stands.
Full reports: `docs/quality/report-full-2026-11-13.md` (after the fix) and
`docs/quality/report-full-2026-11-13-before-guard.md` (before).

## How to run it

```bash
cd nexora-audio
pip install -e ".[dev,qualitylab]"
python -m qualitylab fetch --stt          # pinned public audio + Whisper tiny.en (once)
python -m qualitylab run --profile fast   # 16 cases, about 1 minute: every audio pull request
python -m qualitylab run --profile full   # 242 cases, about 14 minutes on 2 CPUs: nightly
```

A run fails (exit code 1) if an enforced gate fails, a case crashes, or any gate gets worse
than `qualitylab/baseline.json` by more than its tolerance. CI: `.github/workflows/voice-quality.yml`.

## The corpus

| Set | Cases (full) | What it is |
| --- | --- | --- |
| clean | 8 | Speech only: processing must not harm it |
| noise | 180 | 24 speech clips (multiple English speakers) × 15 noises × SNR −5 to 30 dB. Noises: 9 real recordings (air conditioner, airport announcements, babble, copy machine, munching, neighbour/TV, door, typing, vacuum) and 6 synthetic (white, pink, brown, 60 Hz hum, keyboard, music) |
| phone | 12 | The same through a 300–3400 Hz, 8 kHz G.711 μ-law phone line |
| reverb | 6 | Synthetic rooms, RT60 0.3 and 0.6 s, plus noise |
| loss | 16 | 1, 3, 5, 10% packet loss (bursty), each paired with a loss-free twin |
| echo | 12 | Agent speech leaking back through a simulated speakerphone (delay 40/120/250 ms, echo at 0 and −10 dB), agent-only and double-talk |
| turns_tts | 50 | Synthetic English and Arabic caller turns (offline TTS, scripted), one pause each, wideband and 8 kHz phone line; only where generated (`SOURCES.md`) |
| turns | 26 | Speech with inserted pauses of 400–1500 ms, to measure cut-offs and reply delay: 7 inside an unfinished sentence, 11 after a clause the sentence goes on from, 8 cases (16 pauses) between two full sentences (see `E5_SPEC.md`) |

Sources and licences: `qualitylab/SOURCES.md`. Speech-to-text accuracy uses Whisper tiny.en
as a stand-in for the customer's STT, with the clean-speech transcript as reference.

## Finding 1: the default engine was cutting phone speech (fixed)

The first run showed DeepFilterNet3 removing large parts of **clean** speech once it is
narrowband: on 8 kHz phone audio with no noise at all, up to 78% of speech frames were cut
(average 30% across the phone set). Wideband speech was fine (≤ 0.7%). This is the most likely
cause of the "audio cutting" heard on calls. A second, rarer cause: at −5 dB SNR the speech
detector can miss a speaker entirely, and the 40 dB pause gate then deletes the utterance.

**Fix: the speech guard** (`src/nexora_audio/core/speech_guard.py`, on by default,
`speech_guard=True`, margin `speech_guard_margin_db=6`). It tracks the noise floor and, in
frames above it that may be speech (VAD probability ≥ 0.35), never lets the model remove more
than the noise can explain plus 6 dB, restoring any shortfall from the aligned input. It also
keeps the pause gate open in those frames. Thresholds were chosen on the lab: lower
probability thresholds protected slightly more speech but let babble and announcements back
into pauses.

| Phone set (12 cases) | Before | After |
| --- | --- | --- |
| Speech cut, worst case | 77.9% | 3.6% |
| Speech cut, average | 29.5% | 1.4% |
| Intelligibility change, worst case (STOI) | −0.17 | −0.04 |

| Noise set (180 cases) | Before | After |
| --- | --- | --- |
| Speech cut, 95th percentile | 8.4% | 3.0% |
| Speech cut, average | 1.8% | 0.7% |
| Transcription errors after processing (input: 20.1%) | 18.0% | 17.7% |
| Noise in pauses, median (vs input) | −56.0 dB | −54.6 dB |

Cost: slightly more noise is kept where the noise itself sounds like speech (the worst pause
level rose from −31 to −24 dBFS, on airport announcements). That is phase E3 work (N2).

## Where the product stands (full profile, after the fix)

| Gate | Target | Now | Phase |
| --- | --- | --- | --- |
| Audible speech cut, SNR ≥ 0 dB, worst case | ≤ 2% | 5.2% | E3 |
| Intelligibility change, worst case (STOI) | ≥ −0.01 | −0.07 | E3 |
| Transcription on clean speech, WER change | ≤ 0.5 points | 0.8 | E3 |
| Transcription at ≤ 5 dB SNR, fewer errors than raw | ≥ 20% | 14% | E3 |
| Noise in pauses, 0–20 dB SNR, worst case | ≤ −60 dB | −2.5 dB | E3 |
| Loudest noise left in pauses | ≤ −70 dBFS | −24 dBFS | E3 |
| Noise pumping, worst case | ≤ 3 dB | 21 dB | E3 |
| Echo removed (ERLE), worst case | ≥ 30 dB | 0.2 dB (14.4 after E4, median 26.9) | E4 |
| False barge-ins on echo-only audio | 0 | 6 of 6 cases (0 after E4: pass) | E4 |
| Missed barge-ins in double-talk | ≤ 2% | 100% (18.75% after E4) | E4 |
| Caller speech cut while the agent talks | ≤ 3% | 0.7% | pass |
| Mid-sentence pauses taken as end of turn | ≤ 3% | 88% | E5 |
| Reply gap, median | ≤ 800 ms | 704 ms | pass (enforced) |
| Added delay | ≤ 40 ms | 34 ms | pass (enforced) |
| Reported delay matches measured | ≤ 5 ms error | 0.06 ms | pass (enforced) |
| Processing per 20 ms chunk, p99 | ≤ 10 ms | 11 ms with 2 workers sharing 2 CPUs (7–8 ms alone) | E4 |
| Intelligibility lost to 5% packet loss | ≤ 0.05 STOI | 0.09 (0.039 after E2: pass) | E2 |

What the numbers say, in plain words:

- **Steady noise** (fan, hum, white/pink/brown, keyboard) is handled well: pauses clean, speech kept.
- **Speech-like noise** (babble, announcements, TV/neighbour, music) is the main noise gap:
  it is kept as if it were speech, so pauses stay noisy (down only 2–6 dB) and the background
  switches on and off (pumping up to 21 dB). Plan item N2, then E11.
- **Very low SNR (−5 dB)**: speech is still cut in a few cases (worst 25%, copy machine). Plan N1/N4.
- **Echo is not handled at all**: every agent-only case caused a false barge-in, and because of
  that, every real interruption that followed was missed. Phase E4 is required before any
  speakerphone or BYO-WebSocket customer.
- **Turn-taking**: 14 of 16 inserted pauses (400–1200 ms) ended the turn. The pauses were
  inserted at natural word gaps, so the real silence is a little longer than the inserted
  pause; treat 88% as an upper bound. Phase E5.
- **Packet loss**: gaps arrive as silence and cost up to 0.09 STOI at 5% loss. Concealment is phase E2.

## Update after E2 (same day)

E2 (`E2_SPEC.md`) added packet-loss concealment, Opus input, per-call quality numbers and
the Dograh engine. Full-profile re-run (`docs/quality/report-full-2026-11-13-e2.md`):
no gate got worse, and the packet-loss gate now passes.

| Packet loss (paired with the loss-free twin) | Before (worst STOI drop) | After |
| --- | --- | --- |
| 1% | 0.043 | 0.031 |
| 3% | 0.077 | 0.038 |
| 5% (gate ≤ 0.05) | 0.092 | **0.039** |
| 10% | 0.135 | 0.066 |

The single 5% case in the fast profile went from 0.108 to 0.070: better, still above
target, so 10% loss and some 5% patterns remain E3 work (longer gaps fade out by design).

The transcription gates are now reported without a baseline check: the first GitHub run
showed Whisper's output differs between CPU types (noisy-speech WER gain 4.9% there vs
14.3% here), while every other metric matched exactly.

## Update after E4 (2026-11-14)

E4 (`E4_SPEC.md`): echo reference, echo-aware barge-in and the WebRTC AEC3 canceller. The
echo set grew to 28 cases (adds 400 ms delay, echo 6 dB louder than the caller, headsets,
and interruptions in the agent's first second). Echo cases now run with
`echo_cancellation=True`. Report: `docs/quality/report-full-2026-11-14-e4.md`.

| Echo gate | Before E4 | After E4 |
| --- | --- | --- |
| False barge-ins on echo-only audio | 6 of 6 cases | **0** (now enforced) |
| Missed barge-ins in double-talk | 100% | 18.75% (3 of 16, all with echo louder than the caller) |
| Echo removed, worst case | 0.2 dB | 14.4 dB (median 26.9 dB) |
| Caller speech cut while both talk, worst case | 1.2% | 42% (interruption in the agent's first second; median 8.2%) |

The last row is a deliberate trade-off, accepted into the baseline: removing the agent's
echo costs some caller audio while both talk, mostly before the canceller has adapted.
No other gate changed.

## Update after E3 (2026-11-14)

E3 (`E3_SPEC.md`) adds the background-talker gate: speech 17 dB or more below the caller's
level is treated as background and removed in pauses. Report: `docs/quality/report-full-2026-11-14-e3.md`.

| Pause noise, median | Before E3 | After E3 |
| --- | --- | --- |
| Babble | -24.0 dB | -36.8 dB |
| Airport announcements | -44.9 dB | -49.6 dB |
| Phone set | -54.0 dB | -62.8 dB |
| Music | -43.6 dB | -44.4 dB |
| TV / neighbour (as loud as the caller) | -3.9 dB | -3.9 dB (needs E11) |

Speech cut: clean speech average 0.11% → 0.20%; phone worst case unchanged (3.7%).

## Update after E5 (2026-11-14)

E5 (`E5_SPEC.md`) adds Smart Turn v3.2: at each pause it judges whether the caller sounds
finished, and waits 2 s instead of 700 ms when they do not. The turn cases were extended
first: the old ones only paused between two full sentences. Report:
`docs/quality/report-full-2026-11-14-e5.md`.

| Pauses taken as end of turn | Before E5 (700 ms rule) | After E5 |
| --- | --- | --- |
| Inside an unfinished sentence (7) | 71% | 14% (1 of 7) |
| After a clause, sentence goes on (11) | 73% | 36% |
| Between two full sentences (16) | 88% | 75% |
| Reply gap, median / p90 | 650 / 744 ms | 648 / 1328 ms |

The before column is the old rule on the new cases; the old `turn_cutoff` baseline (87.5%)
measured the between-sentence pauses only. Every other gate is unchanged from E3.
`chunk_time` read 11.3 ms with two workers sharing two CPUs; unloaded, the same cases take
5.9 ms with Smart Turn and 5.6 ms without.

## Update after E5b (2026-11-14)

E5b (`E5B_SPEC.md`) lets the caller's transcript hold a turn whose last word cannot end a
sentence. Turn cases now get simulated STT text (Whisper tiny.en) 300 ms into each pause
when the lab runs with STT. All gates unchanged from E5; the new `text_hold` gate (finished
turns held up by the text) is 0%. One E5 test point (`clnsp18`) was moved from inside a
word to the word gap. Report: `docs/quality/report-full-2026-11-14-e5b.md`.

## Update after E5c (2026-11-14)

Synthetic English and Arabic calls (`turns_tts`, 50 cases; `E5B_SPEC.md`). Mid-sentence pauses
taken as end of turn: English 18%, Arabic 5% (silence rule alone: 77% / 80%). Arabic replies
take 1.9 s (median) because Smart Turn hears most finished sentences from this voice as
unfinished (`OPEN_ISSUES.md` I-013). All other gates unchanged. `chunk_time` in this run (52.9
ms) was taken while other test suites shared the CPUs; the baseline keeps 8.8 ms. Report:
`docs/quality/report-full-2026-11-14-e5c.md`.

## Known limits of this baseline

- English speech only; no Arabic yet. No real phone calls, real echo recordings or real
  music yet (they need you; see the plan's open questions).
- Whisper tiny.en is robust to noise, so transcription gains are smaller than a telephony
  STT would show; the gate measures relative change only.
- Echo is simulated (band-limited, overdriven, reverberant speaker path). Real devices will differ.
- Timing gates depend on the machine; they are reported but not regression-checked.
