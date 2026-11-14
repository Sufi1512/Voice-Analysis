# Open issues and bugs

One list for every phase (E1-E11). Each phase logs what it could not finish or fix and
moves on; we fix these together once all phases are done. Numbers are from the quality lab
(`nexora-audio/qualitylab`, full profile) unless stated.

Severity: **high** = callers will notice or a production risk; **medium** = noticeable in
some calls or blocks a target; **low** = cosmetic, tooling or test-only.

| ID | Phase | Severity | Issue | Evidence | Suggested next step |
| --- | --- | --- | --- | --- | --- |
| I-001 | all | high | No real recordings: no real phone calls, speakerphone echo, Arabic callers or music in the lab. All results are on read speech, simulated lines and synthetic voices | `qualitylab/SOURCES.md` | Record 20-50 consented test calls (EN + AR, headset + speakerphone, via each telephony provider) |
| I-002 | E2a/E3 | medium | Speech still cut at low SNR: worst 5.2% audible speech cut (target 2%) | gate `speech_cut` | Fine-tune or swap the model for narrowband/low SNR (needs real calls + GPU) |
| I-003 | E2a | medium | Intelligibility worst case drops (STOI -0.067, target -0.01) | gate `stoi_no_harm` | Same as I-002; check which noise types |
| I-004 | E2a | low | Transcription gain at 5 dB SNR or below is 10.6% fewer errors (target 20%); Whisper tiny.en results differ across CPUs | gate `wer_noisy`; CI vs local | Measure with the customer's real STT |
| I-005 | E3 | high | Background talker as loud as the caller (TV, neighbour) is not removed: pause noise -2.5 dB (target -60) | gates `pause_noise`, `pause_level` | E11 (speaker-aware model) |
| I-006 | E2a/E3 | medium | Noise pumping in pauses up to 21 dB spread (target 3) | gate `pumping` | Smooth the pause gate's gain; check which cases |
| I-007 | E4 | medium | Echo removal worst case 14.4 dB ERLE (target 30) with the near-transparent AEC3 tuning | gate `erle` | Tune AEC3 per device class; test on real speakerphone recordings (I-001) |
| I-008 | E4 | medium | 3 of 16 caller interruptions missed (18.8%) when the echo is 6 dB louder than the caller | gate `missed_barge` | Better double-talk detection, or a learned barge-in model |
| I-009 | E4 | medium | Caller speech cut while the agent talks, worst 44% (early interruption before the echo path is learned) | gate `double_talk_cut` | Faster echo-path learning; a learned barge-in model |
| I-010 | E5 | medium | Mid-sentence pauses still ended as turns: 14% read speech (1 of 7, a simulated STT error), 18% synthetic English (words like "...is", "...with", "...when"); target 3% | gates `turn_cutoff`, `tts_cutoff_en` | Real calls; a text end-of-utterance model with a permissive licence |
| I-011 | E5 | medium | Pauses between two full sentences end the turn 75% of the time (an audio-only judgement) | gates `sentence_pause_cut`, `clause_pause_cut` | Use the STT/LLM's semantic end-of-utterance signal |
| I-012 | E5 | medium | When a finished turn sounds unfinished the caller waits 2 s (read speech p90 reply gap 1.3 s) | E5_SPEC results | Tune `incomplete_silence_ms` per deployment |
| I-013 | E5c | high | Arabic: Smart Turn calls most finished sentences from the synthetic Arabic voice unfinished, so replies take 1.9 s (median) instead of ~0.7 s. Unknown whether it is the voice or the model | gate `tts_reply_gap_ar`; `E5B_SPEC.md` | Test on real Arabic speech; if confirmed, a per-language `TurnConfig` default |
| I-014 | E5c | low | Synthetic voices are research-licence only (Lessac non-commercial; Kareem unclear); fine for internal tests, never ship or train on them | `qualitylab/SOURCES.md` | Replace with consented recordings (I-001) |
| I-015 | E5c | low | The synthetic set needs a second Python environment (`sherpa-onnx==1.12.40`) and is not run in CI | `qualitylab/SOURCES.md` | Cache the generated set as a CI artifact, or add a CI job |
| I-016 | E4/E7 | medium | Native libraries (`librnnoise`, `libdf`, `libnexora_aec`) are built for Linux x86_64 only | `_native/PROVENANCE.md` | E7 |
| I-017 | E6 | medium | Scale-out/in has only been tested in-process (draining, leases, two app instances on a fake Redis); not on a real cluster under load | `nexora-server/tests/test_infra.py` | E10 load test on a real cluster (kind/k3d or cloud) |
| I-018 | E6 | medium | Calls longer than the drain timeout (600 s) are cut when a pod is removed; live audio cannot move between pods | `E6_SPEC.md` | Longer drain for scale-in only, or client-side reconnect with session resume |
| I-019 | E6 | medium | The bundled Redis is single-node; if Redis is down, organization limits fall back to per-pod counts (calls still work) | `deploy/k8s/redis.yaml` | Managed, highly available Redis in production; alert on `nexora_limiter_errors_total` |
| I-020 | E6 | low | `readOnlyRootFilesystem` and the probes have not been tried in a real cluster (only schema-validated) | `tests/test_k8s_manifests.py` | Deploy once to kind/k3d in CI |
| I-021 | E6 | low | The migration Job must be re-created for each image (Jobs are immutable); no Helm hook or Argo sync wave yet | `deploy/k8s/README.md` | Helm chart or a CD pipeline step |
| I-022 | E7 | low | **Explained, fixed:** the live-device test also asserted the slowest chunk < 20 ms, which fails when another process takes the CPU (seen during the soak test: 21.5 ms, still no dropouts). Now it checks dropouts strictly and the slowest chunk against the buffer (80 ms) | `tests/unit/test_devices.py` | none |
| I-023 | E7 | low | Rebuilding `libdf` gives a different (working) binary hash than the bundled one; the other two libraries rebuild byte-identically. Now built with `--locked` and path remapping | `native/build_native.sh` | Rebuild the bundled `libdf` with the script so all hashes reproduce |
| I-024 | E7 | medium | Live microphone/speaker streaming is tested only on a simulated sound card; never on real hardware, Bluetooth headsets or with OS echo cancellation | `tests/unit/test_devices.py` | Run `pytest -m device` and `nexora-audio live` on your machine |
| I-025 | E8 | low | Dashboard: no accessibility audit (screen readers, keyboard-only) beyond semantic HTML and labels; no small-screen layout pass; English only (no Arabic / right-to-left) | `nexora-server/docs/E8_SPEC.md` | Accessibility review; `dir="rtl"` and Arabic strings |
| I-026 | E8 | low | Dashboard shows no live "calls right now" count per organization (instance counters are local; the Redis lease count is not exposed yet) | `limits.py` `cluster_count` | Add `active_sessions` to `/v1/usage` from Redis |
| I-027 | E9 | high | Billing has only run against a simulated Stripe; no real Stripe account, meter or price exists yet | `tests/test_e9.py` | Create a Stripe test-mode meter + price; run `nexora-server billing-report` against it and compare the invoice preview |
| I-028 | E9 | medium | SSO has only run against a simulated OpenID provider; not tried with Google, Entra ID or Okta. SAML is not supported | `tests/test_e9.py` | Register a test app at one provider and sign in once |
| I-029 | E9 | low | Usage pages count a call on the day it started, billing in the hour it ended; a call crossing midnight shows on different days | `docs/E9_SPEC.md` | Show billing-based usage on the Billing page only, or align both on end time |
| I-030 | E9 | low | Sessions that never end cleanly (process killed) keep 0 seconds and are not billed; no sweeper marks them failed | `streaming/ws.py` | Periodic sweep of stale `active` sessions using the lease TTL |
| I-031 | E7 | high | DeepFilterNet's `libdf` built on Apple Silicon (macos-15 runner) dies with "Illegal instruction" in `df_process_frame`; macOS arm64 ships RNNoise + AEC3 only for now (RNNoise fallback, lower quality) | native-libs run 43578822373 | Pin tract/DeepFilterNet dependency versions (the commit's Cargo.lock is stale), or build tract without its hand-written ARM kernels; retest on M-series |
| I-032 | E7 | medium | `libnexora_aec.so` on Linux aarch64 needed glibc 2.38 (C23 `strto*` redirects); shim extended, to be confirmed by the next build's symbol report | native-libs build log | Check `needs glibc > 2.34` line in BUILD_INFO |
| I-033 | E7 | low | AEC3 on Apple Silicon removes 11.6 dB of echo in the unit test vs at least 12 dB on Linux x86/ARM (different SIMD path); marked expected-fail there | native-libs run 43579838586 | Check with real speakerphone audio on a Mac; tune if it matters |
| I-034 | E7 | low | macOS CI VMs: timer jitter caused 5 of 1000 output underruns in the simulated live-device test (slowest chunk only 8.8 ms); allowed up to 1% on macOS | same run | Retest on a real Mac with a real sound card (`pytest -m device`) |
