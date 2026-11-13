# Voice quality report: full profile

Generated 2026-11-13 23:18 UTC by `python -m qualitylab run --profile full`. 276 cases, 70.7 minutes of audio, run time 14.5 minutes. Pipeline settings: `product defaults`; backends: ['deepfilternet3', 'silero-vad', 'voice-enhancer', 'webrtc-aec3']. STT: Whisper tiny.en int8 via sherpa-onnx.

## Gates

| Gate | Phase | Target | Value | Baseline | Status |
| --- | --- | --- | --- | --- | --- |
| Audible speech cut, SNR 0 dB and above (%) | E3 | <= 2 | 5.16 | 5.16 | target (E3) |
| Intelligibility change, worst case (STOI out minus in) | E3 | >= -0.01 | -0.07 | -0.07 | target (E3) |
| Transcription on clean speech: WER change (points) | E3 | <= 0.5 | 0.41 | - | pass |
| Transcription at 5 dB SNR or below: fewer errors than raw (%) | E3 | >= 20 | 10.59 | - | target (E3) |
| Noise left in pauses, SNR 0 to 20 dB, worst case (dB vs input) | E3 | <= -60 | -2.50 | -2.50 | target (E3) |
| Loudest noise left in pauses, any SNR (dBFS; speech is at -26) | E3 | <= -70 | -24.10 | -24.10 | target (E3) |
| Noise pumping in pauses, worst case (dB spread) | E3 | <= 3 | 21.01 | 21.01 | target (E3) |
| Echo removed while only the agent talks, worst case (ERLE dB) | E4 | >= 30 | 14.40 | 14.40 | target (E4) |
| False barge-ins on echo-only audio (count) | E4 | <= 0 | 0.00 | 0.00 | pass |
| Missed barge-ins during double-talk (%) | E4 | <= 2 | 18.75 | 18.75 | target (E4) |
| Caller speech cut while the agent talks, worst case (%) | E4 | <= 3 | 44.44 | 44.44 | target (E4) |
| Mid-sentence pauses taken as end of turn (%) | E5 | <= 3 | 14.29 | 87.50 | target (E5) |
| Pauses after a clause, mid-sentence, taken as end of turn (%) | E5 | <= 20 | 36.36 | - | target (E5) |
| Pauses between two full sentences taken as end of turn (%) | E5 | <= 50 | 75.00 | - | target (E5) |
| Reply gap: end of speech to end-of-turn event, median (ms) | E5 | <= 800 | 648.00 | 704.00 | pass |
| Added delay (ms) | E4 | <= 40 | 34.00 | 34.00 | pass |
| Reported delay matches measured delay, worst error (ms) | E2a | <= 5 | 0.06 | 0.06 | pass |
| Processing time per 20 ms chunk, p99 worst case (ms; inflated when workers share CPUs) | E4 | <= 10 | 11.31 | - | target (E4) |
| Intelligibility lost to 5% packet loss, worst case (STOI drop) | E2 | <= 0.05 | 0.04 | 0.04 | pass |

## Speech sets

| Set | Cases | STOI in → out | SI-SDR in → out (dB) | Speech cut max (%) | Pause noise median (dB) | Under voice median (dB) | WER in → out (%) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| clean | 8 | 1.000 → 0.998 | 145.5 → 6.4 | 0.7 | - | - | 0.0 → 0.4 |
| noise | 180 | 0.876 → 0.907 | 8.8 → 4.7 | 25.4 | -57.9 | 0.7 | 20.1 → 18.4 |
| phone | 12 | 0.872 → 0.862 | 12.6 → 6.7 | 3.7 | -62.8 | 0.4 | 31.6 → 37.4 |
| reverb | 6 | 0.925 → 0.946 | 9.1 → 6.5 | 0.9 | -65.8 | 2.5 | 13.3 → 13.3 |
| loss | 16 | 0.904 → 0.947 | 8.0 → 6.5 | 3.9 | -67.1 | 2.6 | 8.7 → 9.6 |

## Noise set by noise type

| Noise | Cases | STOI Δ mean | Speech cut max (%) | Pause noise worst (dB) | Under voice median (dB) | Pumping max (dB) | WER in → out (%) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| air_conditioner | 12 | 0.035 | 4.5 | -24.7 | 0.7 | 9.2 | 16.8 → 14.0 |
| airport_pa | 12 | 0.039 | 3.0 | -6.3 | 0.1 | 21.0 | 26.9 → 27.9 |
| babble | 12 | 0.036 | 4.8 | -6.3 | 1.5 | 17.5 | 32.8 → 32.1 |
| brown | 12 | -0.006 | 4.0 | -42.7 | -1.5 | 0.5 | 1.7 → 2.0 |
| copy_machine | 12 | 0.036 | 25.4 | -23.4 | -0.2 | 7.7 | 37.4 → 37.2 |
| door | 12 | 0.008 | 1.3 | -11.8 | 1.4 | 12.2 | 3.3 → 4.1 |
| hum | 12 | 0.018 | 2.1 | -23.1 | 0.4 | 2.6 | 3.3 → 2.3 |
| keyboard | 12 | 0.086 | 3.9 | -27.0 | 0.1 | 5.3 | 5.2 → 5.2 |
| munching | 12 | 0.025 | 2.0 | -23.8 | 1.1 | 2.6 | 15.5 → 16.8 |
| music | 12 | 0.019 | 1.4 | -15.5 | 1.4 | 12.7 | 3.8 → 4.8 |
| neighbor | 12 | 0.024 | 2.8 | -2.5 | 0.6 | 16.3 | 57.1 → 44.4 |
| pink | 12 | 0.033 | 0.7 | -46.7 | 0.2 | 0.0 | 24.2 → 20.1 |
| typing | 12 | 0.033 | 3.3 | -31.4 | 0.6 | 2.0 | 9.2 → 7.0 |
| vacuum | 12 | 0.036 | 4.7 | -18.7 | 1.0 | 9.7 | 29.5 → 25.4 |
| white | 12 | 0.050 | 5.2 | -51.9 | -0.8 | 0.0 | 34.2 → 32.2 |

## Noise set by SNR

| SNR (dB) | Cases | STOI in → out | Speech cut max (%) | WER in → out (%) |
| --- | --- | --- | --- | --- |
| -5 | 30 | 0.710 → 0.757 | 25.4 | 53.0 → 52.6 |
| 0 | 30 | 0.793 → 0.854 | 4.5 | 38.0 → 28.8 |
| 5 | 30 | 0.857 → 0.912 | 1.8 | 16.0 → 14.0 |
| 10 | 30 | 0.915 → 0.936 | 5.2 | 10.9 → 11.0 |
| 20 | 30 | 0.981 → 0.987 | 0.9 | 1.5 → 2.7 |
| 30 | 30 | 0.998 → 0.996 | 1.2 | 0.3 → 0.3 |

## Echo set

| Case | kind | delay_ms | echo_db | erle_db | false_barge_ins | missed_barge_in | double_talk_cut_pct | double_talk_stoi |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `echo/single/40ms/+6dB/clnsp5` | single | 40 | 6 | 14.4 | 0 | - | - | - |
| `echo/double/40ms/+6dB/clnsp5` | double | 40 | 6 | - | 0 | 0 | 13.2 | 0.59 |
| `echo/single/40ms/+0dB/clnsp7` | single | 40 | 0 | 28.1 | 0 | - | - | - |
| `echo/double/40ms/+0dB/clnsp7` | double | 40 | 0 | - | 0 | 0 | 6.55 | 0.682 |
| `echo/single/40ms/-10dB/clnsp9` | single | 40 | -10 | 28.3 | 0 | - | - | - |
| `echo/double/40ms/-10dB/clnsp9` | double | 40 | -10 | - | 0 | 0 | 7.16 | 0.717 |
| `echo/single/120ms/+6dB/clnsp11` | single | 120 | 6 | 26.4 | 0 | - | - | - |
| `echo/double/120ms/+6dB/clnsp11` | double | 120 | 6 | - | 0 | 1 | 11.3 | 0.576 |
| `echo/single/120ms/+0dB/clnsp13` | single | 120 | 0 | 29.3 | 0 | - | - | - |
| `echo/double/120ms/+0dB/clnsp13` | double | 120 | 0 | - | 0 | 0 | 11.3 | 0.688 |
| `echo/single/120ms/-10dB/clnsp15` | single | 120 | -10 | 35.8 | 0 | - | - | - |
| `echo/double/120ms/-10dB/clnsp15` | double | 120 | -10 | - | 0 | 0 | 6.92 | 0.785 |
| `echo/single/250ms/+6dB/clnsp17` | single | 250 | 6 | 15.5 | 0 | - | - | - |
| `echo/double/250ms/+6dB/clnsp17` | double | 250 | 6 | - | 0 | 1 | 7.92 | 0.582 |
| `echo/single/250ms/+0dB/clnsp19` | single | 250 | 0 | 80.8 | 0 | - | - | - |
| `echo/double/250ms/+0dB/clnsp19` | double | 250 | 0 | - | 0 | 0 | 6.36 | 0.711 |
| `echo/single/250ms/-10dB/clnsp21` | single | 250 | -10 | 27.4 | 0 | - | - | - |
| `echo/double/250ms/-10dB/clnsp21` | double | 250 | -10 | - | 0 | 0 | 9.43 | 0.766 |
| `echo/single/400ms/+6dB/clnsp23` | single | 400 | 6 | 24.5 | 0 | - | - | - |
| `echo/double/400ms/+6dB/clnsp23` | double | 400 | 6 | - | 0 | 1 | 17 | 0.567 |
| `echo/single/400ms/+0dB/clnsp1` | single | 400 | 0 | 26.3 | 0 | - | - | - |
| `echo/double/400ms/+0dB/clnsp1` | double | 400 | 0 | - | 0 | 0 | 16.8 | 0.621 |
| `echo/single/400ms/-10dB/clnsp3` | single | 400 | -10 | 22.7 | 0 | - | - | - |
| `echo/double/400ms/-10dB/clnsp3` | double | 400 | -10 | - | 0 | 0 | 6.4 | 0.791 |
| `echo/double/0ms/none/clnsp3` | double | 0 | - | - | 0 | 0 | 0.26 | 0.998 |
| `echo/double/0ms/none/clnsp4` | double | 0 | - | - | 0 | 0 | 1.28 | 0.998 |
| `echo/double/120ms/+0dB/at1.6s/clnsp9` | double | 120 | 0 | - | 0 | 0 | 13.9 | 0.623 |
| `echo/double/120ms/-10dB/at1.6s/clnsp10` | double | 120 | -10 | - | 0 | 0 | 44.4 | 0.472 |

## Turns set

| Case | pauses_ms | pauses | pauses_cut | reply_gap_ms |
| --- | --- | --- | --- | --- |
| `turns/clnsp13` | [400, 800] | 2 | 2 | 704 |
| `turns/clnsp14` | [600, 1000] | 2 | 1 | 660 |
| `turns/clnsp15` | [500, 1200] | 2 | 2 | 608 |
| `turns/clnsp16` | [700, 900] | 2 | 1 | 712 |
| `turns/clnsp17` | [400, 800] | 2 | 0 | 2.02e+03 |
| `turns/clnsp18` | [600, 1000] | 2 | 2 | 646 |
| `turns/clnsp19` | [500, 1200] | 2 | 2 | 212 |
| `turns/clnsp20` | [700, 900] | 2 | 2 | 744 |
| `turns-mid/clnsp15@3.30` | [600] | 1 | 0 | 620 |
| `turns-mid/clnsp15@7.76` | [900] | 1 | 0 | 640 |
| `turns-mid/clnsp17@2.15` | [1200] | 1 | 0 | 744 |
| `turns-mid/clnsp18@8.55` | [1500] | 1 | 1 | 650 |
| `turns-mid/clnsp19@7.76` | [600] | 1 | 0 | 224 |
| `turns-mid/clnsp22@1.64` | [900] | 1 | 0 | 572 |
| `turns-mid/clnsp22@10.12` | [1200] | 1 | 0 | 592 |
| `turns-clause/clnsp15@2.25` | [1500] | 1 | 0 | 616 |
| `turns-clause/clnsp15@6.63` | [600] | 1 | 0 | 620 |
| `turns-clause/clnsp16@3.36` | [900] | 1 | 0 | 708 |
| `turns-clause/clnsp17@3.69` | [1200] | 1 | 0 | 744 |
| `turns-clause/clnsp17@5.52` | [1500] | 1 | 1 | 2.04e+03 |
| `turns-clause/clnsp18@6.67` | [600] | 1 | 0 | 654 |
| `turns-clause/clnsp19@8.08` | [900] | 1 | 1 | 212 |
| `turns-clause/clnsp20@5.25` | [1200] | 1 | 0 | 760 |
| `turns-clause/clnsp22@7.34` | [1500] | 1 | 1 | 612 |
| `turns-clause/clnsp22@11.10` | [600] | 1 | 0 | 1.9e+03 |
| `turns-clause/clnsp23@2.80` | [900] | 1 | 1 | 634 |

## Loss set

| Case | loss_pct | lost_fraction | stoi_out | loss_stoi_drop |
| --- | --- | --- | --- | --- |
| `loss/0%/clnsp11` | 0 | - | 0.961 | - |
| `loss/1%/clnsp11` | 1 | 0.0232 | 0.93 | 0.0316 |
| `loss/0%/clnsp12` | 0 | - | 0.962 | - |
| `loss/1%/clnsp12` | 1 | 0.00574 | 0.96 | 0.002 |
| `loss/0%/clnsp13` | 0 | - | 0.943 | - |
| `loss/3%/clnsp13` | 3 | 0.0539 | 0.905 | 0.0382 |
| `loss/0%/clnsp14` | 0 | - | 0.971 | - |
| `loss/3%/clnsp14` | 3 | 0.0157 | 0.969 | 0.0018 |
| `loss/0%/clnsp15` | 0 | - | 0.965 | - |
| `loss/5%/clnsp15` | 5 | 0.0744 | 0.926 | 0.0396 |
| `loss/0%/clnsp16` | 0 | - | 0.977 | - |
| `loss/5%/clnsp16` | 5 | 0.0428 | 0.959 | 0.018 |
| `loss/0%/clnsp17` | 0 | - | 0.963 | - |
| `loss/10%/clnsp17` | 10 | 0.0822 | 0.92 | 0.0426 |
| `loss/0%/clnsp18` | 0 | - | 0.954 | - |
| `loss/10%/clnsp18` | 10 | 0.101 | 0.887 | 0.0664 |
