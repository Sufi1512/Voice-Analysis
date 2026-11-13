import numpy as np
import pytest
from pydantic import ValidationError

from nexora_audio import AudioFormatError, NexoraConfig
from nexora_audio.utils.audio_utils import (
    downmix_mono,
    rms_dbfs,
    to_interleaved,
    to_planar_float32,
)


class TestConfig:
    def test_defaults(self) -> None:
        c = NexoraConfig()
        assert c.sample_rate == 48000 and c.channels == 1 and c.frame_samples == 480
        assert c.requested_features() == ["noise_cancellation", "voice_enhancement"]
        assert c.noise_cancellation_strength == 0.85

    @pytest.mark.parametrize("rate", [11025, 96000, 0])
    def test_rejects_unsupported_rate(self, rate: int) -> None:
        with pytest.raises(ValidationError, match="sample_rate"):
            NexoraConfig(sample_rate=rate)

    def test_rejects_fractional_frame(self) -> None:
        with pytest.raises(ValidationError, match="non-integer"):
            NexoraConfig(sample_rate=22050, frame_ms=10)
        assert NexoraConfig(sample_rate=44100, frame_ms=10).frame_samples == 441

    @pytest.mark.parametrize(
        "field,value",
        [
            ("channels", 3),
            ("frame_ms", 2),
            ("vad_threshold", 1.0),
            ("noise_cancellation_strength", 1.5),
            ("noise_backend", "magic"),
        ],
    )
    def test_rejects_out_of_range(self, field: str, value: object) -> None:
        with pytest.raises(ValidationError):
            NexoraConfig(**{field: value})

    def test_forbids_unknown_fields_and_is_frozen(self) -> None:
        with pytest.raises(ValidationError):
            NexoraConfig(sample_rte=16000)
        c = NexoraConfig()
        with pytest.raises(ValidationError):
            c.sample_rate = 16000  # type: ignore[misc]

    def test_feature_order(self) -> None:
        c = NexoraConfig(vad=True, echo_cancellation=True)
        assert c.requested_features() == [
            "echo_cancellation",
            "noise_cancellation",
            "voice_enhancement",
            "vad",
        ]
        c = NexoraConfig(voice_enhancement=False, auto_gain_control=True)
        assert c.requested_features() == ["noise_cancellation", "auto_gain_control"]


class TestAudioUtils:
    def test_int16_scaling_and_layout(self) -> None:
        x = np.array([[0, 16384], [-32768, 32767]], dtype=np.int16)  # (samples, channels)
        p = to_planar_float32(x)
        assert p.dtype == np.float32 and p.shape == (2, 2)
        np.testing.assert_allclose(p[:, 1], [-1.0, 32767 / 32768])
        np.testing.assert_allclose(p[1, 0], 0.5)

    def test_mono_1d(self) -> None:
        assert to_planar_float32(np.zeros(10)).shape == (1, 10)

    @pytest.mark.parametrize(
        "bad,msg",
        [
            (np.zeros((2, 2, 2)), "1-D or 2-D"),
            (np.zeros(4, dtype=np.uint8), "dtype"),
            (np.array([0.0, np.nan]), "NaN"),
        ],
    )
    def test_rejects_bad_input(self, bad: np.ndarray, msg: str) -> None:
        with pytest.raises(AudioFormatError, match=msg):
            to_planar_float32(bad)

    def test_channel_mismatch(self) -> None:
        with pytest.raises(AudioFormatError, match="expected 2"):
            to_planar_float32(np.zeros(10), channels=2)

    def test_interleaved_int16_roundtrip_and_clip(self) -> None:
        p = np.array([[0.5, -1.0, 2.0]], dtype=np.float32)
        out = to_interleaved(p, np.int16)
        assert out.shape == (3, 1)
        assert out[:, 0].tolist() == [16384, -32768, 32767]

    def test_downmix_and_level(self) -> None:
        st = np.stack([np.ones(100), -np.ones(100)]).astype(np.float32)
        assert np.all(downmix_mono(st) == 0)
        t = np.arange(48000) / 48000
        s = np.sin(2 * np.pi * 1000 * t).astype(np.float32)[None, :]
        assert rms_dbfs(s) == pytest.approx(-3.01, abs=0.01)
        assert rms_dbfs(np.zeros((1, 10), np.float32)) == float("-inf")
