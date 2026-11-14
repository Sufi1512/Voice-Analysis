"""End-to-end: NexoraAudio.process_chunk and process_file, for each noise backend."""

import sys
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from nexora_audio import AudioFormatError, NexoraAudio, NotInitializedError
from tests.audio_fixtures import mix, si_sdr, speech, white

# noise-cancellation quality is measured without EQ/levelling, which SI-SDR would penalise
NC_ONLY = {"voice_enhancement": False, "auto_gain_control": False}


LATENCY_MS = {"deepfilternet3": 30.0, "rnnoise": 20.0}


@pytest.fixture(params=sorted(LATENCY_MS))
def audio(request: pytest.FixtureRequest) -> NexoraAudio:
    if request.param == "deepfilternet3":
        from nexora_audio.backends import deepfilternet as dfn

        if dfn.probe() is not None:
            pytest.skip("DeepFilterNet not available on this platform")
    a = NexoraAudio(sample_rate=48000, noise_backend=request.param, **NC_ONLY)
    a.initialize()
    yield a
    a.close()


def _delay(a: NexoraAudio) -> int:
    return round(a.latency.algorithmic_ms * a.config.sample_rate / 1000)


class TestProcessChunk:
    def test_same_length_for_frame_aligned_chunks(self, audio: NexoraAudio) -> None:
        x = mix(speech(48000), white(len(speech(48000))), 5)[:48000]
        outs = [audio.process_chunk(x[i : i + 480]) for i in range(0, 48000, 480)]
        assert all(o.shape == (480,) and o.dtype == np.float32 for o in outs)
        assert audio.backends == [audio.config.noise_backend]
        assert audio.latency.algorithmic_ms == pytest.approx(LATENCY_MS[audio.backends[0]])
        # 10 ms frames: the typical frame must be far quicker than real time. The 99th
        # percentile mostly measures the scheduler; macOS CI VMs pause processes for
        # 10+ ms (even RNNoise, ~0.1 ms of work, hit 12 ms there; OPEN_ISSUES I-034)
        assert audio.timing.count == 100 and audio.timing.p50_ms < 2.0
        assert audio.timing.p99_ms < (25.0 if sys.platform == "darwin" else 10.0)

    def test_int16_in_int16_out_and_2d_layout(self, audio: NexoraAudio) -> None:
        x = (speech(48000)[:4800] * 20000).astype(np.int16)
        out = audio.process_chunk(x[:, None])
        assert out.dtype == np.int16 and out.shape == (4800, 1)

    def test_improves_speech_at_16k_through_resampling(self) -> None:
        with NexoraAudio(sample_rate=16000, **NC_ONLY) as a:
            clean = speech(16000)
            noisy = mix(clean, white(len(clean)), 0)
            y = np.concatenate(
                [a.process_chunk(noisy[i : i + 160]) for i in range(0, len(noisy), 160)]
                + [a.flush()[:, 0]]
            )
            d = _delay(a)
            n = len(clean)
            before = si_sdr(clean, noisy)
            after = si_sdr(clean, y[d : d + n])
            assert after - before > 8.0, f"{before:.1f} -> {after:.1f}"

    def test_chunk_size_does_not_change_result(self) -> None:
        x = mix(speech(48000), white(len(speech(48000))), 5)[:24000]

        def run(size: int) -> np.ndarray:
            with NexoraAudio() as a:
                parts = [a.process_chunk(x[i : i + size]) for i in range(0, len(x), size)]
                return np.concatenate([*parts, a.flush()[:, 0]])

        a, b = run(480), run(333)
        n = min(len(a), len(b))
        np.testing.assert_allclose(a[:n], b[:n], atol=1e-6)

    def test_reset_and_not_initialized(self, audio: NexoraAudio) -> None:
        x = white(4800) * 0.1
        first = audio.process_chunk(x)
        audio.reset()
        np.testing.assert_array_equal(audio.process_chunk(x), first)
        with pytest.raises(NotInitializedError):
            NexoraAudio().process_chunk(x)

    def test_rejects_wrong_channel_count(self, audio: NexoraAudio) -> None:
        with pytest.raises(AudioFormatError):
            audio.process_chunk(np.zeros((480, 2), np.float32))


class TestProcessFile:
    @pytest.mark.parametrize("rate,channels", [(16000, 1), (44100, 2), (48000, 1)])
    def test_file_roundtrip_aligned_and_cleaner(
        self, audio: NexoraAudio, tmp_path: Path, rate: int, channels: int
    ) -> None:
        clean = speech(rate)
        noisy = mix(clean, white(len(clean)), 0)
        data = np.stack([noisy] * channels, axis=1) if channels == 2 else noisy
        src, dst = tmp_path / "noisy.wav", tmp_path / "clean.wav"
        sf.write(src, data, rate, subtype="PCM_16")

        report = audio.process_file(src, dst)
        out, out_rate = sf.read(dst, dtype="float32", always_2d=True)
        assert out_rate == rate and out.shape == (len(clean), channels)
        assert sf.info(str(dst)).subtype == "PCM_16"
        assert report.frames == len(clean) and report.channels == channels
        assert report.real_time_factor < 1.0 and report.backends == (audio.config.noise_backend,)
        gain = si_sdr(clean, out[:, 0]) - si_sdr(clean, noisy)
        assert gain > 8.0, f"aligned SI-SDR gain only {gain:.1f} dB"

    def test_file_processing_leaves_live_stream_untouched(
        self, audio: NexoraAudio, tmp_path: Path
    ) -> None:
        x = white(4800) * 0.1
        before = audio.process_chunk(x)
        sf.write(tmp_path / "a.wav", white(16000) * 0.1, 16000)
        audio.process_file(tmp_path / "a.wav", tmp_path / "b.wav")
        audio.reset()
        np.testing.assert_array_equal(audio.process_chunk(x), before)

    def test_errors(self, audio: NexoraAudio, tmp_path: Path) -> None:
        sf.write(tmp_path / "x.wav", np.zeros((100, 3)), 16000)
        with pytest.raises(AudioFormatError, match="mono and stereo"):
            audio.process_file(tmp_path / "x.wav", tmp_path / "y.wav")
        sf.write(tmp_path / "m.wav", np.zeros(100), 16000)
        with pytest.raises(AudioFormatError, match="differ"):
            audio.process_file(tmp_path / "m.wav", tmp_path / "m.wav")
        (tmp_path / "bad.wav").write_text("not audio")
        with pytest.raises(AudioFormatError, match="cannot read"):
            audio.process_file(tmp_path / "bad.wav", tmp_path / "o.wav")
