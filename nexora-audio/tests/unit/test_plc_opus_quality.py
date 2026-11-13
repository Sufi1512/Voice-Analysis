"""Packet-loss concealment, Opus input and per-call quality numbers."""

import numpy as np
import pytest

from nexora_audio.streaming import opus
from nexora_audio.streaming.codecs import AudioFormat, StreamDecoder, encode
from nexora_audio.streaming.plc import LossConcealer
from nexora_audio.streaming.quality import QualityMonitor

RATE = 16000


def voiced(seconds: float, f0: float = 150.0, amp: float = 0.2) -> np.ndarray:
    t = np.arange(int(seconds * RATE)) / RATE
    return (amp * sum(np.sin(2 * np.pi * f0 * k * t) / k for k in (1, 2, 3))).astype(np.float32)


def blocks(x: np.ndarray, ms: float = 20) -> list[np.ndarray]:
    n = int(RATE * ms / 1000)
    return [x[i : i + n] for i in range(0, len(x), n)]


def level(x: np.ndarray) -> float:
    return float(10 * np.log10(np.mean(x.astype(np.float64) ** 2) + 1e-12))


def test_zero_gap_after_speech_is_concealed_and_fades() -> None:
    x = voiced(1.0)
    lossy = x.copy()
    lossy[8000:8320] = 0  # one lost 20 ms packet
    lossy[12000:13600] = 0  # 100 ms: longer than the 60 ms fade
    plc = LossConcealer(RATE)
    y = np.concatenate([plc.process(b) for b in blocks(lossy)])
    gap = y[8000:8320]
    assert level(gap) > level(x[8000:8320]) - 3  # the 20 ms gap is filled, not silent
    late = y[12000 + 1120 : 13600]  # after 70 ms of the long gap: faded to silence
    assert not late.any()
    assert level(y[12000:12160]) > level(x[12000:12160]) - 3  # first 10 ms at full level
    assert plc.events == 2
    assert plc.concealed_samples == 320 + int(0.06 * RATE)


def test_real_silence_is_left_alone() -> None:
    plc = LossConcealer(RATE)
    start = np.zeros(4000, np.float32)  # a stream that starts silent
    assert not plc.process(start).any()
    quiet = np.concatenate([np.full(800, 1e-5, np.float32), np.zeros(800, np.float32)])
    assert not plc.process(quiet)[800:].any()  # zeros after inaudible audio: not a loss
    short = voiced(0.1)
    short[500:510] = 0  # 10 zero samples (0.6 ms) are a waveform detail, not a lost packet
    assert np.array_equal(plc.process(short)[500:510], short[500:510])


def test_recovery_crossfades_without_a_step() -> None:
    x = voiced(0.5)
    lossy = x.copy()
    lossy[4000:4320] = 0
    plc = LossConcealer(RATE)
    y = np.concatenate([plc.process(b) for b in blocks(lossy)])
    jump = np.abs(np.diff(y[4310:4340])).max()
    assert jump < 2 * np.abs(np.diff(x)).max()


def test_alaw_silence_counts_as_a_gap() -> None:
    fmt = AudioFormat("alaw", RATE)
    x = voiced(0.5)
    x[4000:4320] = 0
    decoded = StreamDecoder(fmt).decode(encode(x[None, :], fmt))[0]
    assert decoded[4000:4320].any()  # A-law has no exact zero
    plc = LossConcealer(RATE, silence_level=8 / 32768)
    y = np.concatenate([plc.process(b) for b in blocks(decoded)])
    assert plc.events == 1 and level(y[4000:4320]) > level(x[3600:3920]) - 4


def test_signalled_loss_keeps_time() -> None:
    plc = LossConcealer(RATE)
    plc.process(voiced(0.2))
    filled = plc.conceal(320)
    assert len(filled) == 320 and level(filled) > -30
    assert len(LossConcealer(RATE).conceal(160)) == 160  # nothing heard yet: silence


@pytest.mark.skipif(opus.probe() is not None, reason="libopus not installed")
def test_opus_round_trip_and_lost_packet() -> None:
    rate = 16000
    enc = opus.OpusEncoder(rate)
    x = voiced(1.0)
    packets = [enc.encode(b[None, :]) for b in blocks(x) if len(b) == 320]
    dec = StreamDecoder(AudioFormat("opus", rate))
    out = [dec.decode(p) for p in packets[:20]]
    lost = dec.decode(b"")  # packet 20 lost: decoder conceals 20 ms
    out += [lost] + [dec.decode(p) for p in packets[21:]]
    y = np.concatenate([o[0] for o in out])
    assert lost.shape == (1, 320) and level(lost) > level(x) - 10
    assert len(y) == len(packets) * 320
    assert opus.version().startswith("libopus")


def test_opus_format_rules() -> None:
    from nexora_audio.exceptions import AudioFormatError

    with pytest.raises(AudioFormatError):
        AudioFormat("opus", 44100)
    with pytest.raises(AudioFormatError):
        AudioFormat("opus", 16000).bytes_for_ms(20)
    with pytest.raises(AudioFormatError):
        encode(np.zeros((1, 10), np.float32), AudioFormat("opus", 16000))


def test_quality_monitor_numbers() -> None:
    rng = np.random.default_rng(0)
    noise = (0.001 * rng.standard_normal(5 * RATE)).astype(np.float32)  # about -60 dBFS
    x = noise.copy()
    x[RATE : 3 * RATE] += voiced(2.0, amp=0.1)
    x[RATE : RATE + 10] = 1.0  # a few clipped samples
    m = QualityMonitor(RATE)
    for b in blocks(x, 7):  # odd chunk sizes
        m.update(b)
    q = m.summary()
    assert -62 < q["noise_floor_dbfs"] < -58
    assert q["snr_db"] > 30
    assert 30 < q["active_pct"] < 50
    assert q["clipped_pct"] > 0 and q["seconds"] == 5.0


def test_mute_after_speech_is_not_counted_as_loss() -> None:
    x = np.concatenate([voiced(0.5), np.zeros(RATE, np.float32), voiced(0.3)])
    plc = LossConcealer(RATE)
    y = np.concatenate([plc.process(b) for b in blocks(x)])
    assert plc.events == 0 and plc.concealed_samples == 0
    assert not y[8000 + int(0.06 * RATE) : 8000 + RATE].any()  # only a 60 ms fade
