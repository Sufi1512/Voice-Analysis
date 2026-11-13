import itertools

import numpy as np
import pytest

from nexora_audio import (
    ConfigurationError,
    FeatureUnavailableError,
    NexoraAudio,
    NexoraConfig,
    NotInitializedError,
)
from nexora_audio.core.capabilities import BackendRegistry, BackendSpec
from nexora_audio.core.pipeline import Pipeline
from tests.helpers import DelayProcessor, EnergyAnalyzer, GainProcessor, feed_in_chunks, sine


class TestPipeline:
    def test_gain_at_native_rate_is_exact(self) -> None:
        p = Pipeline(48000, 2, [GainProcessor(0.5)])
        x = np.random.default_rng(0).standard_normal((2, 4800)).astype(np.float32)
        y = feed_in_chunks(p.process, x, [100, 480, 999])
        np.testing.assert_allclose(y, 0.5 * x[:, : y.shape[1]], rtol=1e-6)
        assert p.latency.algorithmic_ms == 0.0

    @pytest.mark.parametrize("proc_rate", [48000, 16000])
    def test_measured_delay_matches_reported_latency(self, proc_rate: int) -> None:
        p = Pipeline(48000, 1, [DelayProcessor(64, proc_rate, proc_rate // 100)])
        x = np.zeros((1, 9600), np.float32)
        x[0, 2400] = 1.0
        y = np.concatenate([feed_in_chunks(p.process, x, [480]), p.flush()], axis=1)[0]
        measured = (int(np.argmax(np.abs(y))) - 2400) / 48.0  # ms
        assert measured == pytest.approx(p.latency.algorithmic_ms, abs=1 / 48.0 + 1e-9)

    def test_output_independent_of_chunk_sizes(self) -> None:
        def run(sizes: list[int]) -> np.ndarray:
            p = Pipeline(48000, 1, [GainProcessor(2.0, 16000, 160)])
            x = sine(440, 48000, 0.5)
            return np.concatenate([feed_in_chunks(p.process, x, sizes), p.flush()], axis=1)

        a, b = run([480]), run([17, 1000, 3])
        n = min(a.shape[1], b.shape[1])
        np.testing.assert_allclose(a[:, :n], b[:, :n], atol=1e-5)

    def test_flush_releases_whole_stream(self) -> None:
        p = Pipeline(48000, 1, [GainProcessor(1.0, 16000, 512)])
        out = np.concatenate([p.process(sine(300, 48000, 0.25)), p.flush()], axis=1)
        assert out.shape[1] >= 12000 + p.latency.algorithmic_ms * 48

    def test_analysis_results_and_timestamps(self) -> None:
        p = Pipeline(48000, 2, [GainProcessor(1.0), EnergyAnalyzer(16000, 512)])
        x = np.vstack([sine(500, 48000, 1.0)] * 2)
        feed_in_chunks(p.process, x, [480])
        res = p.pop_results()
        starts = [r.start_sample for r in res]
        assert len(res) == 48000 // 1536
        # the first start is clamped at 0 by the resampler delay, so check spacing after it
        assert all(b - a == 1536 for a, b in itertools.pairwise(starts[1:]))
        assert res[5].values["rms"] == pytest.approx(0.5 / np.sqrt(2), rel=0.01)
        assert p.pop_results() == []

    def test_channel_limit(self) -> None:
        with pytest.raises(ConfigurationError, match="at most 1"):
            Pipeline(48000, 2, [DelayProcessor(1, 48000, 480, channels=1)])


def _registry(available: bool = True) -> BackendRegistry:
    reg = BackendRegistry()
    reg.register(
        BackendSpec(
            "noise_cancellation",
            "broken",
            lambda: "lib missing",
            lambda c: GainProcessor(1.0),
            priority=10,
        )
    )
    reg.register(
        BackendSpec(
            "noise_cancellation",
            "fake",
            (lambda: None) if available else (lambda: "not installed"),
            lambda c: GainProcessor(1.0),
        )
    )
    return reg


class TestClient:
    def test_default_registry_reports_unavailable_and_initialize_raises(self) -> None:
        audio = NexoraAudio()
        caps = audio.capabilities()
        assert set(caps) == {
            "noise_cancellation",
            "voice_isolation",
            "echo_cancellation",
            "auto_gain_control",
            "vad",
        }
        assert not caps["voice_isolation"].available
        with pytest.raises(FeatureUnavailableError) as ei:
            NexoraAudio(registry=BackendRegistry()).initialize()
        assert ei.value.feature == "noise_cancellation"

    def test_falls_back_to_next_available_backend(self) -> None:
        audio = NexoraAudio(registry=_registry())
        assert audio.capabilities()["noise_cancellation"].backend == "fake"
        with audio:
            assert audio.initialized and audio.latency.total_ms >= 0
        assert not audio.initialized

    def test_reports_all_probe_failures(self) -> None:
        status = NexoraAudio(registry=_registry(False)).capabilities()["noise_cancellation"]
        assert not status.available
        assert "broken: lib missing" in status.reason and "fake: not installed" in status.reason

    def test_unknown_preferred_backend(self) -> None:
        audio = NexoraAudio(registry=_registry(), noise_backend="webrtc")
        with pytest.raises(FeatureUnavailableError, match="not registered"):
            audio.initialize()

    def test_voice_isolation_never_silently_ignored(self) -> None:
        audio = NexoraAudio(registry=_registry(), voice_isolation=True)
        with pytest.raises(FeatureUnavailableError, match="voice_isolation"):
            audio.initialize()

    def test_config_errors(self) -> None:
        with pytest.raises(ConfigurationError):
            NexoraAudio(sample_rate=12345)
        with pytest.raises(ConfigurationError, match="either"):
            NexoraAudio(NexoraConfig(), sample_rate=16000)

    def test_latency_requires_initialize_and_close_is_idempotent(self) -> None:
        audio = NexoraAudio(registry=_registry())
        with pytest.raises(NotInitializedError):
            _ = audio.latency
        audio.close()
        audio.close()

    def test_registry_rejects_duplicates_and_unknown_features(self) -> None:
        reg = _registry()
        with pytest.raises(ValueError, match="already"):
            reg.register(
                BackendSpec(
                    "noise_cancellation", "fake", lambda: None, lambda c: GainProcessor(1.0)
                )
            )
        with pytest.raises(ValueError, match="unknown feature"):
            reg.register(BackendSpec("teleport", "x", lambda: None, lambda c: GainProcessor(1.0)))
