import numpy as np
import pytest

from nexora_audio import AudioFormatError
from nexora_audio.core.reframer import Reframer
from nexora_audio.core.resampler import StreamingResampler
from tests.helpers import feed_in_chunks, sine

RNG = np.random.default_rng(1)


class TestReframer:
    @pytest.mark.parametrize("chunk_ms", [10, 20, 32, 40, 7])
    def test_frames_preserve_stream(self, chunk_ms: int) -> None:
        x = RNG.standard_normal((2, 48000)).astype(np.float32)
        r = Reframer(2, 480)
        frames = []
        for i in range(0, x.shape[1], 48 * chunk_ms):
            r.push(x[:, i : i + 48 * chunk_ms])
            while (f := r.pop()) is not None:
                frames.append(f)
        y = np.concatenate([*frames, r.drain()], axis=1)
        np.testing.assert_array_equal(y, x)

    def test_pop_into_preallocated(self) -> None:
        r = Reframer(1, 4)
        r.push(np.arange(10, dtype=np.float32)[None])
        out = np.empty((1, 4), np.float32)
        assert r.pop(out) is out and out.tolist() == [[0, 1, 2, 3]]
        assert r.available == 6 and r.frames_ready == 1

    def test_grows_for_large_push(self) -> None:
        r = Reframer(1, 4, initial_capacity=8)
        big = np.arange(100, dtype=np.float32)[None]
        r.push(big)
        assert r.available == 100
        assert np.array_equal(r.drain(), big)

    def test_shape_check(self) -> None:
        with pytest.raises(AudioFormatError):
            Reframer(2, 4).push(np.zeros((1, 4), np.float32))


def _snr_db(ref: np.ndarray, est: np.ndarray) -> float:
    return float(10 * np.log10(np.sum(ref**2) / np.sum((ref - est) ** 2)))


class TestResampler:
    @pytest.mark.parametrize("rin,rout", [(16000, 48000), (48000, 16000), (44100, 48000)])
    def test_chunking_invariance(self, rin: int, rout: int) -> None:
        x = RNG.standard_normal((2, rin // 2)).astype(np.float32) * 0.1
        one = StreamingResampler(rin, rout, 2)
        whole = np.concatenate([one.process(x), one.flush()], axis=1)
        many = StreamingResampler(rin, rout, 2)
        parts = feed_in_chunks(many.process, x, [1, 7, 160, 333, 480])
        streamed = np.concatenate([parts, many.flush()], axis=1)
        n = min(whole.shape[1], streamed.shape[1])
        np.testing.assert_allclose(streamed[:, :n], whole[:, :n], atol=1e-6)

    @pytest.mark.parametrize("rin,rout", [(16000, 48000), (48000, 16000)])
    def test_sine_fidelity_above_60db(self, rin: int, rout: int) -> None:
        rs = StreamingResampler(rin, rout, 1)
        y = np.concatenate([rs.process(sine(1000, rin, 1.0)), rs.flush()], axis=1)[0]
        d = rs.delay_out_samples
        assert d == int(d)
        ref = sine(1000, rout, 1.0)[0]
        core = slice(1000, len(ref) - 1000)  # ignore filter warm-up at the edges
        assert _snr_db(ref[core], y[int(d) :][core]) > 60.0

    def test_output_length_matches_ratio(self) -> None:
        rs = StreamingResampler(16000, 48000, 1)
        out = rs.process(np.zeros((1, 1600), np.float32))
        assert abs(out.shape[1] - 4800) <= 3

    def test_passthrough(self) -> None:
        rs = StreamingResampler(48000, 48000, 1)
        x = np.ones((1, 10), np.float32)
        assert rs.process(x) is x and rs.delay_out_samples == 0.0


@pytest.mark.parametrize("rin,rout", [(16000, 48000), (48000, 16000), (8000, 48000), (48000, 8000)])
def test_fast_integer_path_matches_general_path(rin: int, rout: int) -> None:
    x = RNG.standard_normal((2, rin // 3)).astype(np.float32) * 0.1
    fast = StreamingResampler(rin, rout, 2)
    slow = StreamingResampler(rin, rout, 2, fast=False)
    sizes = [1, 7, 160, 333, 480]
    a = np.concatenate([feed_in_chunks(fast.process, x, sizes), fast.flush()], axis=1)
    b = np.concatenate([feed_in_chunks(slow.process, x, sizes), slow.flush()], axis=1)
    n = min(a.shape[1], b.shape[1])
    assert abs(a.shape[1] - b.shape[1]) <= 3
    np.testing.assert_allclose(a[:, :n], b[:, :n], atol=2e-6)
