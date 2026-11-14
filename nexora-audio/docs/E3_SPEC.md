# E3: noise and phone audio (spec and results)

Phase E3 of `VOICE_QUALITY_PLAN.md`, approved by the user on 2026-11-14 ("Okry" to
starting E3 after E4).

## Starting point (lab, after E4)

Steady noise (fans, hum, white/pink/brown, typing, vacuum) was already handled well:
pauses 60-68 dB quieter, speech intact. The gaps were all **speech-like background**:

| Background | Pause noise, median | Pumping, worst |
| --- | --- | --- |
| TV / neighbour | -3.9 dB | 16.3 dB |
| Door bangs | -19.9 dB | 12.2 dB |
| Babble | -24.0 dB | 17.5 dB |
| Music | -43.6 dB | 12.7 dB |
| Airport announcements | -44.9 dB | 21.0 dB |

The voice detector calls any voice "speech", so the pause gate stayed open and the speech
guard protected it.

## What E3 adds: the background-talker gate (plan item N2)

`core/talker_gate.py`, on by default (`background_speech_db=17`).

- **What counts as background.** It follows the caller's level: the 80th percentile of
  the cleaned speech level over the last 4 s. Speech more than 17 dB below that is
  background.
- **What happens to background.** It is removed in pauses. The speech guard does not
  restore it, and DeepFilterNet3 gets no speech cap there.
- **A new speaker.** After 8 s of background only, that voice becomes the speaker, so a
  quieter caller is not silenced for long.
- **What it judges.** The guarded output, because DeepFilterNet3 alone under-reads
  narrowband speech. Judging the raw output first cut phone speech up to 39%.
- **How the defaults were chosen** (lab, 9 noise/phone/clean groups):

| Setting | Babble pauses | Phone pauses | Clean speech cut, mean | Phone cut, worst |
| --- | --- | --- | --- | --- |
| Off | -24.0 dB | -54.0 dB | 0.11% | 3.6% |
| 15 dB | -38.4 dB | -70.3 dB | 0.54% | 4.5% |
| **17 dB (default)** | **-36.8 dB** | **-62.8 dB** | **0.20%** | **3.7%** |
| 20 dB | -25.2 dB | -57.3 dB | 0.14% | 3.7% |
| 17 dB, faster release (50 ms) | -44.1 dB | -75.7 dB | 1.10% | 8.2% |

The faster release cleaned more but cut more of the caller's soft speech, so it was
rejected: not cutting speech comes first.

## What E3 does not fix (and why)

- **Background as loud as the caller** (TV, babble or announcements at 0 dB SNR) cannot
  be told apart by level. This drives the worst-case pause and pumping numbers. Fixing it
  needs a model of the caller's voice: phase E11.
- **Very low SNR (-5 dB).** The voice detector sometimes misses speech; the worst case is
  copy-machine noise.
- **Scattered word-ending cuts** on one speaker (clnsp19) at 10 dB: about 5% of frames.
- **Not built, for lack of test material:**
  - Automatic gain for quiet calls (N1 level part): the corpus has no quiet-caller cases.
  - A hum notch: hum is already removed by 68 dB.
  - A narrowband model fine-tune (N3): it needs real phone recordings and a GPU.

## Full-profile result

258 cases, `docs/quality/report-full-2026-11-14-e3.md`. No gate got worse except two small
changes, both recorded in the baseline:

- **Double-talk cut, worst case: 42.1% → 44.4%.** This is one case: an interruption in the
  agent's first second at -10 dB echo. The median moved from 8.2% to 8.7%.
- **Noisy-speech transcription gain (report-only): 14.5% → 10.6%.** Mostly one case, TV
  noise at -5 dB SNR, where Whisper's output is garbage either way: 38 errors → 76, on 37
  words.

Worst-case pause and pumping numbers are unchanged: they come from background as loud as
the caller (E11).


## Pause-noise pumping: what it is made of (bug round, 2026-11-14, I-006)

The `pumping` gate (output level spread in pauses, worst 21 dB, target 3) also counts the
noise's own swing. A new metric subtracts it: `pumping_added_db` = output spread minus input
spread in the same pauses; gate `pumping_added` (share of noise cases over 3 dB, report-only,
in the full baseline). Full profile: **23 of 180 noise cases (12.8%)** get more than 3 dB
added:

| Noise | Cases | Cause |
| --- | --- | --- |
| babble, neighbour, airport announcements, music | 16 | Background talkers / speech-like noise: the speech detector opens on it, the noise remover partly keeps it. This is I-005 (E11: needs a trained model) |
| door slams | 3 | The detector opens on the slam; the slam passes at the speech cap |
| vacuum, air conditioner, copy machine | 4 | At 0 to -5 dB SNR (noise as loud as the voice or louder) the detector or the speech guard opens the gate on the noise |

Tried on the steady and impulsive noises (vacuum, air conditioner, copy machine, door,
keyboard; 60 cases): a pause gate of 20 or 10 dB instead of 40 changes the worst pumping by
less than 0.1 dB (the noise remover already silences these pauses; the swing comes from the
moments the gate opens) and lets more noise through (median pause noise -61 → -54 / -48 dB).
A stricter speech guard (9 dB margin instead of 6) lowers it by 0.5-1.5 dB. Neither is worth
it: the openings are the speech protection working at very low SNR, and not cutting the
caller's voice comes first. No defaults changed.
