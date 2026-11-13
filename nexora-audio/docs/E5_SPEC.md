# E5: turn-taking (spec and results)

Phase E5 of `VOICE_QUALITY_PLAN.md` (item C2), approved by the user on 2026-11-14 ("Yes" to
starting E5 after E3).

## Starting point

A turn ended after 700 ms of silence, for every sentence. In the lab that took 87.5% of
inserted pauses as the end of the turn (gate `turn_cutoff`), with a 704 ms median reply gap.

## What E5 adds: Smart Turn v3.2 (on by default)

- **The model.** Smart Turn v3.2 by Daily, BSD-2-Clause (code, weights and data), bundled
  unchanged from the `pipecat-ai` 1.16.0 wheel: `_models/smart-turn-v3.2-cpu.onnx` (8.7 MB,
  int8) and its numpy Whisper feature code `backends/_whisper_features.py`. Notices:
  `THIRD_PARTY_NOTICES.md`; checksums: `_native/PROVENANCE.md`. It listens to the last 8 s
  of the turn and gives the probability that the turn is finished, from intonation and the
  shape of the last words. No text is needed.
- **When it runs.** Once per pause: at `speech_end` (300 ms of silence), on the cleaned
  caller audio from 300 ms before the turn's first word **up to the last voiced frame**.
  About 45 ms of CPU, single-threaded, in the session's processing thread, so the chunk
  where the caller pauses comes back about 45 ms late (it is silence). p99 chunk time is
  unchanged (5.9 ms vs 5.6 ms without it, unloaded).
- **What it changes** (`TurnConfig`):

| Verdict | Turn ends after | Setting |
| --- | --- | --- |
| Finished (probability >= 0.5) | 700 ms of silence | `complete_silence_ms` |
| Unfinished | 2000 ms of silence | `incomplete_silence_ms` |
| No verdict (model missing, error, under 0.1 s of audio) | 700 ms | `end_of_turn_ms` |

  With the defaults Smart Turn never ends a turn sooner than the old rule. It only waits
  longer when the caller sounds unfinished, which matches the priority "do not cut the
  caller". For a snappier agent set `complete_silence_ms=300` (see the table below for what
  that costs). `end_of_turn` events carry `complete_probability`.
- **End of stream.** `flush()` closes a turn that is still waiting (for example a caller who
  hangs up mid-pause) with an `end_of_turn` marked `stream_end: true`. The lab ignores these.
- **Off switch.** `TurnConfig(smart_turn=False)` restores the old rule exactly.

### Why the audio stops at the last voiced frame

Measured on the clean clips (Smart Turn alone): with the audio cut at the last word, it
called grammatically unfinished points complete 1 time in 7; with 300 ms of trailing
silence, 4 times in 7. Sentence ends stayed high either way (88% vs 88%).

## The lab had to change first

All 16 pauses the old turn cases inserted fell **between two full sentences**, e.g.
"...tell me its name. | Y'all should have let me do it." (checked with Whisper). No audio
model can know the caller will go on there, so that test could not show whether we cut
people off mid-sentence. The turns set now has three kinds, labelled by grammar alone
(never by what a turn model says), from Whisper transcripts checked by hand
(`qualitylab/corpus.py`, `MID_SENTENCE_POINTS`, `CLAUSE_POINTS`):

| Kind | Example | Cases | Gate |
| --- | --- | --- | --- |
| `mid`: the words so far cannot be a sentence | "...ten years ago they \| blew up some of our ditches" | 7 | `turn_cutoff` (target 3%) |
| `clause`: could be a sentence, but it goes on | "his captain was thin and haggard \| and his beautiful boots..." | 11 | `clause_pause_cut` (target 20%) |
| `sentence`: between two full sentences (the old cases) | "...tell me its name. \| Y'all should..." | 8 (16 pauses) | `sentence_pause_cut` (target 50%) |

Pauses are 0.4-1.5 s, in 25 dB pink noise. The reply gap is measured on all 26 cases.

## Results (lab, 26 turn cases)

| Setting | Unfinished cut | Clause cut | Between-sentence cut | Reply gap median / p90 |
| --- | --- | --- | --- | --- |
| Old rule, 700 ms | 71% | 73% | 88% | 650 / 744 ms |
| Smart Turn, finished ends at 300 ms | 29% | 55% | 75% | 264 / 1136 ms |
| Smart Turn, finished ends at 500 ms | 29% | 55% | 75% | 456 / 1232 ms |
| Smart Turn, threshold 0.7, 500 ms | 14% | 36% | 62% | 460 / 1964 ms |
| **Smart Turn, 700 ms (default)** | **14%** | **36%** | **75%** | **648 / 1328 ms** |

The full 276-case run with these defaults: every other gate unchanged from E3 (`QUALITY_BASELINE.md`, E5 update; report `docs/quality/report-full-2026-11-14-e5.md`).

## Known limits

- **Not at the 3% target.** One of the 7 unfinished points is still cut, and about a third of
  clause pauses. The sample is small (18 hand-labelled points from 9 read-speech clips);
  read audiobook speech also has stronger "finished" intonation at commas than
  conversation. Real call recordings are needed to trust these numbers.
- **Between full sentences** the turn ends about 3 times in 4. That is a judgement call any
  audio-only model has to make; the next step is the STT's text ("...and um", "to") and the
  provider's own end-of-utterance signal (plan C2, third bullet).
- **Slow replies when it is wrong the other way.** When a finished turn sounds unfinished,
  the caller waits 2 s (p90 reply gap 1.3 s).
- **Languages.** Arabic and other languages have not been tested yet (plan C4); the lab only
  has English read speech.
- **Recovery in Pipecat/Dograh.** If the turn ends too early and the caller goes on, Pipecat
  treats the new speech as an interruption and cancels the reply in progress, so the agent
  does not keep talking over them; the wasted LLM call remains.

## Tests

- `tests/unit/test_codecs_turns.py::TestSmartTurnJudge`: fast end when finished, long wait
  when unfinished, fallback for no verdict or a failing judge, judge span ends at the last
  voiced window, a resumed turn is judged again, probability in the event, model checksum.
- `tests/integration/test_stream_session.py`: 8 kHz G.711 sessions get verdicts (resampled
  to 16 kHz); `smart_turn=False` gives none.
