# Quality lab: test audio and models

Nothing below is committed to the repository. `python -m qualitylab fetch --stt` downloads
it into `qualitylab/.cache/` (gitignored), at a pinned commit or release, so every run uses
the same audio. The files are used only for internal testing and are never shipped.

| Item | Source (pinned) | Licence | Used for |
| --- | --- | --- | --- |
| JFK inaugural excerpt, 11 s | `tests/fixtures/jfk_inaugural_16k.wav` (already in the repo) | Public domain (US federal government work) | Speech |
| 24 clean speech clips (`clean_test/clnsp0-23.wav`), 16 kHz, multiple English speakers per clip | [microsoft/MS-SNSD](https://github.com/microsoft/MS-SNSD) at commit `fe61c4ba0d9ac8dd7e23d719cc79f8947e1dc742` | Repository MIT. Speech per its README: PTDB-TUG (ODbL 1.0) and Edinburgh 56-speaker dataset (its own licence) | Speech |
| 11 noise recordings (`noise_test/`): air conditioner, airport announcements, babble, copy machine, munching, neighbour, shutting door, typing, vacuum | Same commit | Per the MS-SNSD README: Freesound clips with CC0, and DEMAND (CC BY-SA 3.0) | Real noise |
| Whisper tiny.en, int8 ONNX | [k2-fsa/sherpa-onnx release `asr-models`, `sherpa-onnx-whisper-tiny.en.tar.bz2`](https://github.com/k2-fsa/sherpa-onnx/releases/tag/asr-models) | Whisper weights MIT (OpenAI); sherpa-onnx Apache-2.0 | Transcription-accuracy gate |

Generated in code with fixed seeds (no third-party audio): white, pink, brown noise, 60 Hz
mains hum, keyboard clicks, an instrumental music stand-in, synthetic rooms (reverb),
speakerphone echo paths, the 300-3400 Hz G.711 phone line and packet loss.

**Before any of this audio is used beyond internal testing** (for example to train or
fine-tune a model we ship), confirm the per-file licences. In particular DEMAND is
share-alike and the Edinburgh dataset has its own terms.

**Not yet in the corpus** (needs you, see the plan's open questions): real phone calls
through each telephony provider, real speakerphone echo recordings, Arabic and other
launch languages, real music.
