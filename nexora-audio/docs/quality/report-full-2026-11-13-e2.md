# Voice quality report: full profile

Generated 2026-11-13 17:55 UTC by `python -m qualitylab run --profile full`. 242 cases, 61.4 minutes of audio, run time 14.2 minutes. Pipeline settings: `product defaults`; backends: ['deepfilternet3', 'silero-vad', 'voice-enhancer']. STT: Whisper tiny.en int8 via sherpa-onnx.

## Gates

| Gate | Phase | Target | Value | Baseline | Status |
| --- | --- | --- | --- | --- | --- |
| Audible speech cut, SNR 0 dB and above (%) | E3 | <= 2 | 5.16 | 5.16 | target (E3) |
| Intelligibility change, worst case (STOI out minus in) | E3 | >= -0.01 | -0.07 | -0.07 | target (E3) |
| Transcription on clean speech: WER change (points) | E3 | <= 0.5 | 1.23 | - | target (E3) |
| Transcription at 5 dB SNR or below: fewer errors than raw (%) | E3 | >= 20 | 14.55 | - | target (E3) |
| Noise left in pauses, SNR 0 to 20 dB, worst case (dB vs input) | E3 | <= -60 | -2.50 | -2.50 | target (E3) |
| Loudest noise left in pauses, any SNR (dBFS; speech is at -26) | E3 | <= -70 | -24.10 | -24.10 | target (E3) |
| Noise pumping in pauses, worst case (dB spread) | E3 | <= 3 | 21.01 | 21.01 | target (E3) |
| Echo removed while only the agent talks, worst case (ERLE dB) | E4 | >= 30 | 0.20 | 0.20 | target (E4) |
| False barge-ins on echo-only audio (count) | E4 | <= 0 | 6.00 | 6.00 | target (E4) |
| Missed barge-ins during double-talk (%) | E4 | <= 2 | 100.00 | 100.00 | target (E4) |
| Caller speech cut while the agent talks, worst case (%) | E4 | <= 3 | 0.67 | 0.67 | pass |
| Mid-sentence pauses taken as end of turn (%) | E5 | <= 3 | 87.50 | 87.50 | target (E5) |
| Reply gap: end of speech to end-of-turn event, median (ms) | E5 | <= 800 | 704.00 | 704.00 | pass |
| Added delay (ms) | E4 | <= 40 | 34.00 | 34.00 | pass |
| Reported delay matches measured delay, worst error (ms) | E2a | <= 5 | 0.06 | 0.06 | pass |
| Processing time per 20 ms chunk, p99 worst case (ms; inflated when workers share CPUs) | E4 | <= 10 | 11.60 | - | target (E4) |
| Intelligibility lost to 5% packet loss, worst case (STOI drop) | E2 | <= 0.05 | 0.04 | 0.09 | pass |

## Speech sets

| Set | Cases | STOI in → out | SI-SDR in → out (dB) | Speech cut max (%) | Pause noise median (dB) | Under voice median (dB) | WER in → out (%) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| clean | 8 | 1.000 → 0.999 | 145.5 → 6.4 | 0.4 | - | - | 0.0 → 1.2 |
| noise | 180 | 0.876 → 0.907 | 8.8 → 4.7 | 25.4 | -54.5 | 0.7 | 20.1 → 17.7 |
| phone | 12 | 0.872 → 0.864 | 12.6 → 6.7 | 3.6 | -54.0 | 0.4 | 31.6 → 39.6 |
| reverb | 6 | 0.925 → 0.947 | 9.1 → 6.5 | 0.4 | -62.3 | 2.5 | 13.3 → 13.3 |
| loss | 16 | 0.904 → 0.947 | 8.0 → 6.5 | 3.9 | -62.8 | 2.6 | 8.7 → 8.9 |

## Noise set by noise type

| Noise | Cases | STOI Δ mean | Speech cut max (%) | Pause noise worst (dB) | Under voice median (dB) | Pumping max (dB) | WER in → out (%) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| air_conditioner | 12 | 0.036 | 4.5 | -24.7 | 0.7 | 9.2 | 16.8 → 13.5 |
| airport_pa | 12 | 0.039 | 3.0 | -6.3 | 0.1 | 21.0 | 26.9 → 26.9 |
| babble | 12 | 0.036 | 4.8 | -6.3 | 1.5 | 17.5 | 32.8 → 31.8 |
| brown | 12 | -0.006 | 4.0 | -42.7 | -1.5 | 0.5 | 1.7 → 2.0 |
| copy_machine | 12 | 0.036 | 25.4 | -23.4 | -0.2 | 7.7 | 37.4 → 37.2 |
| door | 12 | 0.008 | 1.3 | -11.2 | 1.4 | 12.2 | 3.3 → 3.3 |
| hum | 12 | 0.018 | 2.1 | -22.0 | 0.4 | 2.6 | 3.3 → 2.5 |
| keyboard | 12 | 0.086 | 3.9 | -20.8 | 0.1 | 5.3 | 5.2 → 5.0 |
| munching | 12 | 0.025 | 2.0 | -20.9 | 1.1 | 3.2 | 15.5 → 17.0 |
| music | 12 | 0.020 | 1.4 | -15.3 | 1.4 | 12.7 | 3.8 → 5.3 |
| neighbor | 12 | 0.024 | 2.2 | -2.5 | 0.6 | 16.3 | 57.1 → 34.9 |
| pink | 12 | 0.034 | 0.5 | -45.1 | 0.2 | 0.0 | 24.2 → 22.6 |
| typing | 12 | 0.033 | 2.9 | -5.3 | 0.6 | 2.8 | 9.2 → 6.5 |
| vacuum | 12 | 0.037 | 4.7 | -17.8 | 1.0 | 9.7 | 29.5 → 24.7 |
| white | 12 | 0.050 | 5.2 | -48.2 | -0.8 | 0.0 | 34.2 → 31.9 |

## Noise set by SNR

| SNR (dB) | Cases | STOI in → out | Speech cut max (%) | WER in → out (%) |
| --- | --- | --- | --- | --- |
| -5 | 30 | 0.710 → 0.757 | 25.4 | 53.0 → 48.9 |
| 0 | 30 | 0.793 → 0.854 | 4.5 | 38.0 → 28.4 |
| 5 | 30 | 0.857 → 0.913 | 1.8 | 16.0 → 14.0 |
| 10 | 30 | 0.915 → 0.936 | 5.2 | 10.9 → 11.3 |
| 20 | 30 | 0.981 → 0.988 | 0.7 | 1.5 → 2.5 |
| 30 | 30 | 0.998 → 0.996 | 0.5 | 0.3 → 0.4 |

## Echo set

| Case | kind | delay_ms | echo_db | erle_db | false_barge_ins | missed_barge_in | double_talk_cut_pct | double_talk_stoi |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `echo/single/40ms/+0dB/clnsp5` | single | 40 | 0 | 2.3 | 1 | - | - | - |
| `echo/double/40ms/+0dB/clnsp5` | double | 40 | 0 | - | 1 | 1 | 0.67 | 0.809 |
| `echo/single/40ms/-10dB/clnsp7` | single | 40 | -10 | 1 | 1 | - | - | - |
| `echo/double/40ms/-10dB/clnsp7` | double | 40 | -10 | - | 1 | 1 | 0 | 0.941 |
| `echo/single/120ms/+0dB/clnsp9` | single | 120 | 0 | 0.5 | 1 | - | - | - |
| `echo/double/120ms/+0dB/clnsp9` | double | 120 | 0 | - | 1 | 1 | 0 | 0.708 |
| `echo/single/120ms/-10dB/clnsp11` | single | 120 | -10 | 0.2 | 1 | - | - | - |
| `echo/double/120ms/-10dB/clnsp11` | double | 120 | -10 | - | 1 | 1 | 0 | 0.949 |
| `echo/single/250ms/+0dB/clnsp13` | single | 250 | 0 | 1.6 | 1 | - | - | - |
| `echo/double/250ms/+0dB/clnsp13` | double | 250 | 0 | - | 1 | 1 | 0 | 0.801 |
| `echo/single/250ms/-10dB/clnsp15` | single | 250 | -10 | 0.7 | 1 | - | - | - |
| `echo/double/250ms/-10dB/clnsp15` | double | 250 | -10 | - | 1 | 1 | 0 | 0.934 |

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
| `loss/0%/clnsp11` | 0 | - | 0.962 | - |
| `loss/1%/clnsp11` | 1 | 0.0232 | 0.931 | 0.0312 |
| `loss/0%/clnsp12` | 0 | - | 0.963 | - |
| `loss/1%/clnsp12` | 1 | 0.00574 | 0.961 | 0.002 |
| `loss/0%/clnsp13` | 0 | - | 0.944 | - |
| `loss/3%/clnsp13` | 3 | 0.0539 | 0.906 | 0.0383 |
| `loss/0%/clnsp14` | 0 | - | 0.971 | - |
| `loss/3%/clnsp14` | 3 | 0.0157 | 0.969 | 0.0019 |
| `loss/0%/clnsp15` | 0 | - | 0.966 | - |
| `loss/5%/clnsp15` | 5 | 0.0744 | 0.926 | 0.0392 |
| `loss/0%/clnsp16` | 0 | - | 0.977 | - |
| `loss/5%/clnsp16` | 5 | 0.0428 | 0.958 | 0.0181 |
| `loss/0%/clnsp17` | 0 | - | 0.963 | - |
| `loss/10%/clnsp17` | 10 | 0.0822 | 0.92 | 0.0426 |
| `loss/0%/clnsp18` | 0 | - | 0.954 | - |
| `loss/10%/clnsp18` | 10 | 0.101 | 0.887 | 0.0664 |
