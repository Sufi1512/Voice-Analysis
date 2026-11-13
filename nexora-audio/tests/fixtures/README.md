# Test fixtures

| File | Content | Source | Licence |
|---|---|---|---|
| `jfk_inaugural_16k.wav` | 11 s excerpt of John F. Kennedy's inaugural address (1961), 16 kHz mono PCM16 | `samples/jfk.wav` from https://github.com/ggml-org/whisper.cpp (sha256 `59dfb9a4acb36fe2a2affc14bacbee2920ff435cb13cc314a08c13f66ba7860e`) | Public domain: a speech delivered by the US President in his official capacity is a work of the US federal government |

Noise for tests is generated in code (white, pink and brown noise, keyboard-like clicks)
with fixed random seeds, so no third-party noise recordings are needed.
