# Third-party notices

nexora-audio includes or links to the following third-party software.

## RNNoise (bundled binary: `_native/linux-x86_64/librnnoise.so`)
Source: https://github.com/xiph/rnnoise, release v0.2 (includes the default model).
See `_native/PROVENANCE.md` for build details and checksums.

```
Copyright (c) 2007-2017, 2024 Jean-Marc Valin
Copyright (c) 2023 Amazon
Copyright (c) 2017, Mozilla
Copyright (c) 2005-2017, Xiph.Org Foundation
Copyright (c) 2003-2004, Mark Borgerding

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions
are met:

- Redistributions of source code must retain the above copyright
notice, this list of conditions and the following disclaimer.

- Redistributions in binary form must reproduce the above copyright
notice, this list of conditions and the following disclaimer in the
documentation and/or other materials provided with the distribution.

- Neither the name of the Xiph.Org Foundation nor the names of its
contributors may be used to endorse or promote products derived from
this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
``AS IS'' AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
A PARTICULAR PURPOSE ARE DISCLAIMED.  IN NO EVENT SHALL THE FOUNDATION
OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

## DeepFilterNet (bundled binary `_native/linux-x86_64/libdf.so` and model `_models/DeepFilterNet3_onnx.tar.gz`)
Source: https://github.com/Rikorose/DeepFilterNet. Code and model weights are dual-licensed
MIT OR Apache-2.0. nexora-audio uses them under the MIT licence:

```
The MIT License (MIT)
Copyright (c) 2021 Hendrik Schröter

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
```

The library also statically links Rust crates (tract, ndarray and others) from crates.io
under their own permissive licences (MIT and/or Apache-2.0). Run `cargo license` in the
upstream repository to list them.

## Silero VAD (bundled model `_models/silero_vad.onnx`, from silero-vad 6.2.3)

```
MIT License

Copyright (c) 2020-present Silero Team

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## WebRTC AudioProcessing / AEC3 (bundled binary `_native/linux-x86_64/libnexora_aec.so`)

WebRTC AudioProcessing v2.1 (PulseAudio's standalone build), used for echo cancellation.
Copyright (c) 2011, Google Inc. All rights reserved. BSD-3-Clause: full text in
`_native/licenses/webrtc-COPYING.txt`; Google's additional patent grant in
`_native/licenses/webrtc-PATENTS.txt`.

## Abseil (compiled into `libnexora_aec.so`)

Abseil C++ `20240722.0`, Copyright The Abseil Authors. Apache License 2.0: full text in
`_native/licenses/abseil-LICENSE.txt`. Unmodified.

## Smart Turn v3.2 (bundled model `_models/smart-turn-v3.2-cpu.onnx`) and Whisper features (`backends/_whisper_features.py`)

End-of-turn model by Daily (https://github.com/pipecat-ai/smart-turn); code, weights and
training data are BSD 2-Clause. Copied unchanged from the `pipecat-ai` 1.16.0 wheel
(`pipecat/audio/turn/smart_turn/data/` and `pipecat/audio/turn/smart_turn/_whisper_features.py`).
Copyright (c) 2024-2026, Daily. Full licence text: `_native/licenses/pipecat-smart-turn-LICENSE.txt`.

`_whisper_features.py` contains portions derived from Hugging Face Transformers
(`WhisperFeatureExtractor`), Copyright 2022-2023 The HuggingFace Inc. team and the librosa &
torchaudio authors, Apache License 2.0 (full text: `_native/licenses/apache-2.0.txt`),
modified by Daily. nexora-audio does not modify the file further.

## onnxruntime (dependency, MIT)

## Optional dependencies (installed separately, not bundled)
- soundfile (BSD-3-Clause); its wheels bundle libsndfile (LGPL-2.1), loaded dynamically.
- sounddevice (MIT); its Windows/macOS wheels bundle PortAudio (MIT-style licence).
- numpy, scipy (BSD-3-Clause); pydantic (MIT).
