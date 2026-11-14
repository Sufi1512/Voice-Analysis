# E5b: the transcript as a second end-of-turn cue (spec)

Follow-up to E5 (`E5_SPEC.md`), started 2026-11-14 at the user's request ("do this", after
E5's results named this as the next step). Plan item C2, third bullet: "use the STT's own
end-of-utterance signal and text".

## Problem

Smart Turn judges from sound alone. A caller who stops after "...a lot of" or "...because"
has plainly not finished, but read speech often sounds finished there. Every voice agent
already has the caller's transcript from its speech-to-text, so the words can help.

## Rule

When the last word of the caller's latest transcript is one that **cannot end an English or
Arabic sentence**, the turn waits `incomplete_silence_ms` (2 s), whatever the audio says.
The text only ever makes the agent wait longer. It never ends a turn sooner, because a
sentence that ends on any other word may or may not be finished.

The word list is fixed by grammar class (written before measuring; see "Honesty" below):

| Class | English | Arabic |
| --- | --- | --- |
| Conjunctions | and, or, but, nor, because, if, unless, although, whereas, than | و، أو، لكن، ثم، لأن، إذا / اذا |
| Articles, possessives | a, an, the, my, your, our, their, its, his | |
| Prepositions that need an object | of, to, into, onto, through, via, toward, towards, between, among, during, per | في، من، إلى / الى، على، عن، مع |
| Subject pronouns | I, we, they, he, she | |
| Relative words | | اللي، الذي، التي، الذين، أن |
| Fillers | um, uh, uhm, er, erm | يعني |

Not on the list, on purpose, because a turn can end on them: modals ("yes, I can"), "for",
"from", "in", "on", "with", "like", "her", "that", "so", "hmm" and "بس" ("stop!").

Matching: the last token of the text, lower-cased, with punctuation and quotes removed (STT
adds a full stop at every pause). `TurnConfig(text_cue=False)` turns the rule off.

## How the transcript arrives

- SDK: `StreamSession.push_transcript(text)`: the caller's latest interim or final text for
  the current turn. It is ignored when no turn is open (a late final for a finished turn
  must not hold up the next one) and cleared when a new turn starts. Within a turn it stands
  until a newer transcript replaces it: the voice detector can still be catching up with
  the last words when the STT sends them, so clearing it on "speech again" lost the cue
  (found by a server test). If the caller goes on and the STT is slow to send the new
  words, the turn waits longer: the safe direction.
- Server, Process mode: the client sends `{"type": "transcript", "text": "..."}`.
- Server, Relay mode: the agent sends the same message on its socket. Nexora uses it and
  does not forward it to the caller.
- A transcript arriving during the silence takes effect straight away: if the turn has not
  ended yet, it now waits the full 2 s.

## Lab method

For each turn case the lab transcribes, with Whisper tiny.en (the lab's stand-in STT), the
clean speech from the start of the turn to each pause, and to the true end. It pushes that
text 300 ms into the pause, like a streaming STT's final result. Measured: the three pause
kinds from E5, the reply gap, and how often a **finished** turn is held for 2 s by the text
(`text_hold` on the true ends: the cost of the rule).

## Honesty

The 7 unfinished-sentence lab points were known when the list was written (they end on
"of", "they", "through", "his", "can", "boots", "love"). The list is built from grammar
classes, and "can" is left out on purpose, but the lab number for that kind is still an
optimistic one. The between-sentence and true-end cases are the fairer test of the
rule's cost. Arabic is untested: there is no Arabic speech in the lab yet.

## Results (2026-11-14)

Lab, 26 turn cases, simulated STT text pushed 300 ms into each pause:

| Setting | Unfinished cut | Clause cut | Between-sentence cut | Reply gap median / p90 |
| --- | --- | --- | --- | --- |
| Silence rule only | 71% | 73% | 88% | 650 / 744 ms |
| Silence rule + text cue | 43% | 73% | 88% | 650 / 744 ms |
| Smart Turn (E5) | 14% | 36% | 75% | 648 / 1328 ms |
| Smart Turn + text cue (default) | 14% | 36% | 75% | 648 / 1328 ms |

Cost: 0 of 26 finished turns were held up by the text (`text_hold` 0%).

Wider check, without hand-picked points: every word gap of 40 ms or more in all 24 clips
(342 gaps). The transcript ended on an unfinished word at 23 of them, and Smart Turn already
said "not finished" at all 23. At the 24 true ends the text never said "unfinished".

**Verdict.** On English read speech the cue adds nothing on top of Smart Turn, but it
costs nothing either. It stays on by default as a backup: when Smart Turn is off or
unavailable (it then cuts mid-sentence cut-offs from 71% to 43%), for fillers ("um", rare in
read speech), and for Arabic, where Smart Turn is untested. Real calls will show whether it
earns its place.

The remaining unfinished cut is a simulated-STT error: at "...the legend states, can |
expect", Whisper tiny heard "...can it?", so the cue had nothing to catch. The cue is only
as good as the customer's STT.

**Lab fix found on the way.** The E5 point `clnsp18@8.55` was inside the word "ex|pect", not
in the gap after "can". It is now at 8.37 s, the gap between the words (energy dips to
-48 dB there). It is still the one unfinished case being cut, so the E5 numbers do not
change.

## Synthetic English and Arabic calls (E5c, 2026-11-14)

No real recordings are available, so the lab now generates scripted caller turns with
offline text-to-speech (`qualitylab/tts_scripts.py`, `tts_gen.py`; voices and licences in
`qualitylab/SOURCES.md`). Because the script is known, every pause point and the transcript
are exact, with no hand-labelling.

- 12 unfinished-sentence turns per language: half end on a word in the text-cue list
  ("...a flight to", "...ممكن تساعدني في"), half do not ("...my account number is",
  "...رقم الحساب هو", "...started when"). 4 two-sentence turns per language.
- Two ways to make the pause: **comma** (synthesised with a comma, so the voice keeps a
  "going on" tone) and **split** (the first part synthesised alone, so it ends on a falling,
  finished-sounding tone: a caller trailing off). Comma cut points are kept only when they
  fall where the first part ends when spoken alone (within 10% + 60 ms); 6 failed that and
  were dropped, leaving 50 cases. Pause points were also checked with Whisper.
- Pauses 0.6-1.5 s; alternating a wideband line with 25 dB pink noise and an 8 kHz u-law
  phone line with 20 dB pink noise. Perfect transcripts pushed 300 ms into the pause.

| Setting | EN unfinished cut | AR unfinished cut | Between-sentence cut (EN / AR) | Reply gap median, EN / AR |
| --- | --- | --- | --- | --- |
| Silence rule only | 77% | 80% | 75% / 75% | 690 / 677 ms |
| Silence rule + text cue | 45% | 25% | 75% / 75% | 690 / 677 ms |
| Smart Turn only | 36% | 25% | 75% / 75% | 696 / 1902 ms |
| **Smart Turn + text cue (default)** | **18%** | **5%** | 75% / 75% | 696 / **1902** ms |
| Default, long wait 1.5 s | 32% | 30% | 75% / 75% | 696 / 1046 ms |
| Default, long wait 1.2 s | 41% | 50% | 75% / 75% | 696 / 734 ms |

What this shows:

- **The text cue earns its place here**: with Smart Turn it halves English cut-offs
  (36% → 18%) and Arabic ones (25% → 5%), at no cost to reply speed. On this set it is
  not redundant, unlike on the read-speech set.
- **English cut-offs left** are at words not on the list ("...is", "...with", "...when",
  where a sentence can also end) said with a finished-sounding tone.
- **Arabic replies are slow**: Smart Turn calls most *finished* Arabic sentences from this
  voice unfinished (probabilities 0.01-0.4), so the caller waits 2 s. Whether that is this
  synthetic voice (undiacritised text, a Jordanian voice fine-tuned from an English one) or
  Smart Turn itself, only real Arabic speech can say. Shortening the long wait trades it
  straight back into cut-offs (table). Logged in `OPEN_ISSUES.md`; defaults unchanged.

Gates: `tts_cutoff_en`, `tts_cutoff_ar` (target 3%), `tts_reply_gap_en`, `tts_reply_gap_ar`
(target 800 ms), report-only. They only run where the synthetic set has been generated
(not in CI).
