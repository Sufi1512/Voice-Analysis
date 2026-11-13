# Voice quality report: full profile

Generated 2026-11-13 16:41 UTC by `python -m qualitylab run --profile full`. 242 cases, 61.4 minutes of audio, run time 13.7 minutes. Pipeline settings: `{'speech_guard': False}`; backends: ['deepfilternet3', 'silero-vad', 'voice-enhancer']. STT: Whisper tiny.en int8 via sherpa-onnx.

## Gates

| Gate | Phase | Target | Value | Baseline | Status |
| --- | --- | --- | --- | --- | --- |
| Audible speech cut, SNR 0 dB and above (%) | E3 | <= 2 | 77.88 | - | target (E3) |
| Intelligibility change, worst case (STOI out minus in) | E3 | >= -0.01 | -0.17 | - | target (E3) |
| Transcription on clean speech: WER change (points) | E3 | <= 0.5 | 0.82 | - | target (E3) |
| Transcription at 5 dB SNR or below: fewer errors than raw (%) | E3 | >= 20 | 12.62 | - | target (E3) |
| Noise left in pauses, SNR 0 to 20 dB, worst case (dB vs input) | E3 | <= -60 | -4.40 | - | target (E3) |
| Loudest noise left in pauses, any SNR (dBFS; speech is at -26) | E3 | <= -70 | -31.20 | - | target (E3) |
| Noise pumping in pauses, worst case (dB spread) | E3 | <= 3 | 17.77 | - | target (E3) |
| Echo removed while only the agent talks, worst case (ERLE dB) | E4 | >= 30 | 0.30 | - | target (E4) |
| False barge-ins on echo-only audio (count) | E4 | <= 0 | 6.00 | - | target (E4) |
| Missed barge-ins during double-talk (%) | E4 | <= 2 | 100.00 | - | target (E4) |
| Caller speech cut while the agent talks, worst case (%) | E4 | <= 3 | 9.31 | - | target (E4) |
| Mid-sentence pauses taken as end of turn (%) | E5 | <= 3 | 87.50 | - | target (E5) |
| Reply gap: end of speech to end-of-turn event, median (ms) | E5 | <= 800 | 704.00 | - | pass |
| Added delay (ms) | E4 | <= 40 | 34.00 | - | pass |
| Reported delay matches measured delay, worst error (ms) | E2a | <= 5 | 0.06 | - | pass |
| Processing time per 20 ms chunk, p99 worst case (ms; inflated when workers share CPUs) | E4 | <= 10 | 8.48 | - | pass |
| Intelligibility lost to 5% packet loss, worst case (STOI drop) | E2 | <= 0.05 | 0.10 | - | target (E2) |

## Speech sets

| Set | Cases | STOI in → out | SI-SDR in → out (dB) | Speech cut max (%) | Pause noise median (dB) | Under voice median (dB) | WER in → out (%) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| clean | 8 | 1.000 → 0.999 | 145.5 → 6.4 | 0.7 | - | - | 0.0 → 0.8 |
| noise | 180 | 0.876 → 0.925 | 8.8 → 5.4 | 37.3 | -56.0 | 0.3 | 20.1 → 17.9 |
| phone | 12 | 0.872 → 0.828 | 12.6 → 5.6 | 77.9 | -54.0 | -0.1 | 31.6 → 40.0 |
| reverb | 6 | 0.925 → 0.954 | 9.1 → 6.6 | 0.6 | -62.5 | 2.2 | 13.3 → 10.6 |
| loss | 16 | 0.904 → 0.931 | 8.0 → 6.5 | 15.9 | -63.1 | 2.3 | 8.7 → 9.3 |

## Noise set by noise type

| Noise | Cases | STOI Δ mean | Speech cut max (%) | Pause noise worst (dB) | Under voice median (dB) | Pumping max (dB) | WER in → out (%) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| air_conditioner | 12 | 0.054 | 4.5 | -32.1 | 0.3 | 5.6 | 16.8 → 26.0 |
| airport_pa | 12 | 0.049 | 13.4 | -12.0 | -0.4 | 17.8 | 26.9 → 25.7 |
| babble | 12 | 0.057 | 14.4 | -12.5 | 1.0 | 14.7 | 32.8 → 29.5 |
| brown | 12 | -0.008 | 6.4 | -42.7 | -1.5 | 0.5 | 1.7 → 2.0 |
| copy_machine | 12 | 0.061 | 37.3 | -34.0 | -0.8 | 4.0 | 37.4 → 37.2 |
| door | 12 | 0.015 | 1.7 | -11.7 | 1.1 | 8.1 | 3.3 → 4.3 |
| hum | 12 | 0.019 | 3.5 | -22.0 | 0.3 | 2.6 | 3.3 → 3.3 |
| keyboard | 12 | 0.136 | 7.7 | -20.6 | -1.0 | 0.7 | 5.2 → 3.2 |
| munching | 12 | 0.062 | 5.2 | -20.9 | -0.7 | 3.2 | 15.5 → 14.0 |
| music | 12 | 0.041 | 2.4 | -15.3 | 0.5 | 10.2 | 3.8 → 4.6 |
| neighbor | 12 | 0.041 | 11.7 | -4.4 | -0.3 | 14.2 | 57.1 → 33.4 |
| pink | 12 | 0.054 | 0.5 | -45.1 | -0.1 | 0.0 | 24.2 → 22.9 |
| typing | 12 | 0.058 | 8.4 | -26.7 | -1.1 | 2.0 | 9.2 → 6.0 |
| vacuum | 12 | 0.051 | 4.7 | -27.0 | 0.8 | 9.3 | 29.5 → 23.2 |
| white | 12 | 0.048 | 8.4 | -48.2 | -0.8 | 0.0 | 34.2 → 33.7 |

## Noise set by SNR

| SNR (dB) | Cases | STOI in → out | Speech cut max (%) | WER in → out (%) |
| --- | --- | --- | --- | --- |
| -5 | 30 | 0.710 → 0.805 | 37.3 | 53.0 → 51.9 |
| 0 | 30 | 0.793 → 0.892 | 5.2 | 38.0 → 26.7 |
| 5 | 30 | 0.857 → 0.932 | 3.5 | 16.0 → 14.7 |
| 10 | 30 | 0.915 → 0.936 | 9.9 | 10.9 → 10.5 |
| 20 | 30 | 0.981 → 0.988 | 2.6 | 1.5 → 2.6 |
| 30 | 30 | 0.998 → 0.996 | 1.8 | 0.3 → 0.3 |

## Echo set

| Case | kind | delay_ms | echo_db | erle_db | false_barge_ins | missed_barge_in | double_talk_cut_pct | double_talk_stoi |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `echo/single/40ms/+0dB/clnsp5` | single | 40 | 0 | 2.7 | 1 | - | - | - |
| `echo/double/40ms/+0dB/clnsp5` | double | 40 | 0 | - | 1 | 1 | 1.01 | 0.821 |
| `echo/single/40ms/-10dB/clnsp7` | single | 40 | -10 | 1.1 | 1 | - | - | - |
| `echo/double/40ms/-10dB/clnsp7` | double | 40 | -10 | - | 1 | 1 | 0.29 | 0.951 |
| `echo/single/120ms/+0dB/clnsp9` | single | 120 | 0 | 1 | 1 | - | - | - |
| `echo/double/120ms/+0dB/clnsp9` | double | 120 | 0 | - | 1 | 1 | 9.31 | 0.706 |
| `echo/single/120ms/-10dB/clnsp11` | single | 120 | -10 | 0.3 | 1 | - | - | - |
| `echo/double/120ms/-10dB/clnsp11` | double | 120 | -10 | - | 1 | 1 | 0.56 | 0.947 |
| `echo/single/250ms/+0dB/clnsp13` | single | 250 | 0 | 1.7 | 1 | - | - | - |
| `echo/double/250ms/+0dB/clnsp13` | double | 250 | 0 | - | 1 | 1 | 0.36 | 0.833 |
| `echo/single/250ms/-10dB/clnsp15` | single | 250 | -10 | 0.7 | 1 | - | - | - |
| `echo/double/250ms/-10dB/clnsp15` | double | 250 | -10 | - | 1 | 1 | 0 | 0.938 |

## Turns set

| Case | pauses_ms | pauses | pauses_cut | reply_gap_ms |
| --- | --- | --- | --- | --- |
| `turns/clnsp13` | [400, 800] | 2 | 2 | 704 |
| `turns/clnsp14` | [600, 1000] | 2 | 2 | 660 |
| `turns/clnsp15` | [500, 1200] | 2 | 2 | 608 |
| `turns/clnsp16` | [700, 900] | 2 | 2 | 712 |
| `turns/clnsp17` | [400, 800] | 2 | 1 | 712 |
| `turns/clnsp18` | [600, 1000] | 2 | 2 | 646 |
| `turns/clnsp19` | [500, 1200] | 2 | 1 | - |
| `turns/clnsp20` | [700, 900] | 2 | 2 | 744 |

## Loss set

| Case | loss_pct | lost_fraction | stoi_out | loss_stoi_drop |
| --- | --- | --- | --- | --- |
| `loss/0%/clnsp11` | 0 | - | 0.965 | - |
| `loss/1%/clnsp11` | 1 | 0.0232 | 0.92 | 0.0452 |
| `loss/0%/clnsp12` | 0 | - | 0.968 | - |
| `loss/1%/clnsp12` | 1 | 0.00574 | 0.956 | 0.0122 |
| `loss/0%/clnsp13` | 0 | - | 0.95 | - |
| `loss/3%/clnsp13` | 3 | 0.0539 | 0.87 | 0.0801 |
| `loss/0%/clnsp14` | 0 | - | 0.972 | - |
| `loss/3%/clnsp14` | 3 | 0.0157 | 0.96 | 0.0118 |
| `loss/0%/clnsp15` | 0 | - | 0.969 | - |
| `loss/5%/clnsp15` | 5 | 0.0744 | 0.867 | 0.102 |
| `loss/0%/clnsp16` | 0 | - | 0.978 | - |
| `loss/5%/clnsp16` | 5 | 0.0428 | 0.928 | 0.0496 |
| `loss/0%/clnsp17` | 0 | - | 0.967 | - |
| `loss/10%/clnsp17` | 10 | 0.0822 | 0.851 | 0.116 |
| `loss/0%/clnsp18` | 0 | - | 0.957 | - |
| `loss/10%/clnsp18` | 10 | 0.101 | 0.817 | 0.14 |
