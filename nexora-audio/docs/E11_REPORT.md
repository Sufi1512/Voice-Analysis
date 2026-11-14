# E11: background voice cancellation, research spike (go/no-go report)

Phase E11 of `ENTERPRISE_PLAN.md`, run 2026-11-14 on the user's instruction to build the
remaining phases in order. Question: can we remove **other people's voices** (a TV, a
colleague, a neighbour as loud as the caller), not only noise? Today's pipeline removes
background talkers that are 17 dB or more quieter than the caller (E3); voices as loud as
the caller pass through untouched (`OPEN_ISSUES.md` I-005).

## Decision

- **No-go** for shipping a speaker-embedding gate (the only approach buildable now from
  permissively licensed parts). Measured on 44 call mixes, it removes too little of the other
  voice, cuts too much of the caller and costs too much CPU (numbers below).
- **Go**, if the product needs this feature, for a **training project**: a personalised
  noise-suppression model (DeepFilterNet conditioned on the caller's voice, the
  "pDeepFilterNet" approach), trained on permissively licensed speech. It needs a GPU,
  licensed multi-speaker data, about 6-10 weeks and real call recordings to validate
  (plan below). No off-the-shelf model meets the licence + real-time + quality bar.

## 1. Survey (2026-11)

| Option | What it is | Verdict |
| --- | --- | --- |
| Target-speaker extraction toolkits (WeSep, SpeakerBeam, SpEx+) | Research code that extracts one speaker given an enrolment clip; WeSep's authors note that open pretrained models are scarce | Research models, mostly non-causal, pretrained weights tied to their training data's licence. Not deployable as is |
| Personalised enhancement papers (Personalized PercepNet, pDeepFilterNet2, personalised DeepVQE, Logitech's real-time extractor) | Real-time models conditioned on a speaker embedding; exactly the product shape | Papers only: no released model under a licence we could ship |
| Blind separation (SepFormer, MossFormer2 and similar) | Splits a mix into N voices | Offline/heavy, and still needs to pick which voice is the caller; separation models are usually trained on licensed corpora (WSJ0) |
| **Speaker embedding + gate (tested)** | Recognise the caller's voice, mute others | Buildable now: 3D-Speaker ERes2Net (Apache-2.0) via sherpa-onnx. Measured below |

Speaker-embedding models checked for the gate (same-speaker vs different-speaker cosine
similarity on 1.5 s windows of the lab's 24 English clips):

| Model (licence) | Same speaker, median / 10th pct | Different speakers, median / 90th pct | Time per 1.5 s |
| --- | --- | --- | --- |
| WeSpeaker ResNet34, VoxCeleb (code Apache-2.0, weights follow VoxCeleb CC-BY-4.0) | 0.72 / 0.59 | 0.39 / 0.60 | 44 ms |
| **3D-Speaker ERes2Net, VoxCeleb (Apache-2.0)** | 0.59 / 0.45 | 0.08 / 0.25 | 63 ms |

The gate used 3D-Speaker; its threshold (0.35) was set from this table **before** testing.

## 2. Test set (44 mixes, 16 kHz)

11 caller/background pairs:

- 6 pairs of different real speakers from the lab's MS-SNSD clips; "different" was judged by
  WeSpeaker, a different model from the one the gate uses;
- 3 pairs of synthetic single-speaker voices (Piper lessac, ryan, alan);
- 2 mixed pairs.

Each pair in 4 scenarios, with pink noise 30 dB below speech:

- **pause, 0 dB**: the other voice talks only while the caller is silent, as loud as the caller;
- **pause, -6 dB**: the same, 6 dB quieter;
- **overlap, -6 dB**: a TV under the caller from 4 s on;
- **solo**: the caller alone (control: the gate must cut nothing).

The caller always speaks first, so the gate can learn their voice (about 3 s).

## 3. Results (`spikes/e11_speaker_gate.py`, raw: `docs/quality/e11-speaker-gate-results.json`)

The speaker gate runs causally on the output of today's full pipeline.

| Scenario (11 mixes each) | Other voice left in the caller's pauses: today | with the gate | Caller speech cut by the gate, median / worst |
| --- | --- | --- | --- |
| Pause, 0 dB | 0.0 dB (not removed) | -3.4 dB | **13.2% / 27.7%** |
| Pause, -6 dB | 0.0 dB | -3.5 dB | 12.2% / 27.7% |
| Overlap, -6 dB | -1.0 dB | -1.3 dB | 0.0% / 9.7% |
| Solo (control) | - | - | 0.0% / 0.0% |

The "cut" column counts caller frames the gate made more than 10 dB quieter than the
pipeline's own output.

Faster settings (to rule out bad tuning), pause scenario at 0 dB:

| Window / step / confirmations | Other voice left, median (best) | Caller cut, median / worst | Caller-alone cut, worst | CPU per call |
| --- | --- | --- | --- | --- |
| 1.5 s / 0.25 s / 2 (as above) | -3.6 dB (-7.3) | 13.2% / 20.7% | 0.0% | ~13% of a core |
| 1.0 s / 0.25 s / 1 | -4.8 dB (-8.7) | 11.7% / 17.1% | 4.9% | ~8% |
| 0.8 s / 0.1 s / 2 | -7.2 dB (-11.2) | 11.0% / 16.5% | 11.0% | ~16% |
| 0.6 s / 0.1 s / 2 | -8.8 dB (-12.8) | 12.4% / 18.7% | 11.9% | ~12% |

Why it fails:

- **Too slow to recognise a voice.** It needs roughly 0.6-1.5 s of the other voice before it
  can say "not the caller", so most of a short phrase leaks through. When the caller speaks
  again, the window still holds the other voice, so the caller's first words are muted.
- **Shorter windows** react faster but confuse the caller with someone else (up to 12% of
  a caller speaking alone muted).
- **Overlap cannot be fixed by gating at all**: muting would mute the caller too.
- **Too expensive**: 8-16% of a CPU core per call on top of today's pipeline, which already
  runs at about 2 calls per core (`nexora-server/docs/E10_RESULTS.md`).

## 4. If we go ahead: training plan for a personalised model

| Item | Plan |
| --- | --- |
| Model | DeepFilterNet3 (already our engine, MIT/Apache-2.0) with a speaker embedding injected (pDeepFilterNet2-style), causal, about 10-20 ms frames; the caller's voice learnt from the first seconds of the call or an enrolment clip |
| Training data (permissive) | Clean speech: LibriTTS-R or LibriSpeech (CC-BY-4.0), VCTK (CC-BY-4.0), plus Arabic speech with a commercial-use licence (to be found); speaker embeddings: 3D-Speaker (Apache-2.0); noise: DNS-challenge noise (check per-file licences), our synthetic noises. Interfering talkers mixed on the fly at -10 to +5 dB, including overlap |
| Compute | 1-2 GPUs (24-80 GB) for roughly 1-2 weeks of training runs |
| Effort | 6-10 weeks: data pipeline 2, training and tuning 3-4, integration (streaming, enrolment, fallback) 1-2, evaluation 1-2 |
| Acceptance | On this test set and on real recorded calls: other voice in pauses at least 20 dB down, overlap at least 10 dB down, caller speech cut 2% or less (E2a's gate), solo callers untouched, CPU per call at most 1.5x today |
| Risks | The caller's voice learnt from a noisy start; two callers sharing a phone; Arabic data with a usable licence; CPU cost |

## 5. What stays true today

- Background talkers **17 dB or more quieter** than the caller are removed in pauses (E3).
- Voices as loud as the caller are **not** removed (I-005). Customers who need this today
  would need a headset mic or a different product until the training project is done.

Sources:
[WeSep paper (arXiv 2409.15799)](https://arxiv.org/abs/2409.15799),
[Personalized PercepNet (Interspeech 2021)](https://www.isca-archive.org/interspeech_2021/giri21_interspeech.pdf),
[pDeepFilterNet2 (arXiv 2404.08022)](https://arxiv.org/html/2404.08022v1),
[Personalized speech enhancement without a separate speaker embedding model (arXiv 2406.09928)](https://arxiv.org/html/2406.09928v1),
[Logitech real-time personalised speaker extraction (Interspeech 2022)](https://www.isca-archive.org/interspeech_2022/ronssin22_interspeech.pdf),
[WeSpeaker pretrained model licences](https://wenet-e2e.github.io/wespeaker/pretrained.html),
[sherpa-onnx speaker embedding models](https://huggingface.co/csukuangfj/speaker-embedding-models/tree/main).
