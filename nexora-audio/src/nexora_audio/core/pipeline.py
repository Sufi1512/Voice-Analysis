"""Processing pipeline: chains processors and adapts rates and frame sizes between them."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from nexora_audio.core.processor import AnalysisResult, Processor, ProcessorKind
from nexora_audio.core.reframer import Reframer
from nexora_audio.core.resampler import StreamingResampler
from nexora_audio.exceptions import AudioFormatError, ConfigurationError
from nexora_audio.utils.audio_utils import Float32Array, downmix_mono


@dataclass(frozen=True, slots=True)
class LatencyReport:
    """Latency the pipeline adds, from first input sample to matching output sample.

    ``algorithmic_ms``: fixed signal delay (processor look-ahead + resampling filters).
    ``buffering_ms``: worst-case extra wait for frames to fill, given input chunks
    of one sample. Feeding chunks that are multiples of the frame size reduces it.
    """

    algorithmic_ms: float
    buffering_ms: float

    @property
    def total_ms(self) -> float:
        return self.algorithmic_ms + self.buffering_ms


class _Stage:
    """One processor plus the resampler and reframer that feed it."""

    def __init__(self, processor: Processor, in_rate: int, channels: int) -> None:
        self.processor = processor
        self.channels = channels
        native = processor.native_sample_rate
        self.resampler = (
            StreamingResampler(in_rate, native, channels) if in_rate != native else None
        )
        self.reframer = Reframer(channels, processor.native_frame_size)
        self._frame: Float32Array = np.empty(
            (channels, processor.native_frame_size), dtype=np.float32
        )
        self.frames_done = 0

    @property
    def resampler_delay_native(self) -> float:
        return self.resampler.delay_out_samples if self.resampler else 0.0

    def run(self, chunk: Float32Array) -> Float32Array:
        x = self.resampler.process(chunk) if self.resampler else chunk
        self.reframer.push(x)
        n = self.reframer.frames_ready
        if n == 0:
            return np.zeros((self.channels, 0), dtype=np.float32)
        fs = self.processor.native_frame_size
        out = np.empty((self.channels, n * fs), dtype=np.float32)
        for i in range(n):
            self.reframer.pop(self._frame)
            out[:, i * fs : (i + 1) * fs] = self.processor.process(self._frame)
        self.frames_done += n
        return out

    def reset(self) -> None:
        if self.resampler:
            self.resampler.reset()
        self.reframer.reset()
        self.processor.reset()
        self.frames_done = 0


class Pipeline:
    """Runs audio through TRANSFORM processors in order, then through ANALYSIS taps.

    Accepts chunks of any length at ``sample_rate`` and returns processed audio at
    the same rate. Output length per call varies because of frame buffering; over a
    whole stream (after :meth:`flush`) every input sample comes out, delayed by
    :attr:`latency`.
    """

    def __init__(self, sample_rate: int, channels: int, processors: Sequence[Processor]) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self._transforms: list[_Stage] = []
        self._analysis: list[_Stage] = []

        rate = sample_rate
        for proc in processors:
            if proc.kind is ProcessorKind.TRANSFORM:
                if channels > proc.max_channels:
                    raise ConfigurationError(
                        f"{proc.name} supports at most {proc.max_channels} channel(s)"
                    )
                self._transforms.append(_Stage(proc, rate, channels))
                rate = proc.native_sample_rate
        self._out_resampler = (
            StreamingResampler(rate, sample_rate, channels) if rate != sample_rate else None
        )
        for proc in processors:
            if proc.kind is ProcessorKind.ANALYSIS:
                self._analysis.append(_Stage(proc, sample_rate, 1))

        self._results: list[AnalysisResult] = []
        self.samples_in = 0
        self.samples_out = 0

    @property
    def processors(self) -> list[Processor]:
        return [s.processor for s in self._transforms + self._analysis]

    @property
    def latency(self) -> LatencyReport:
        algo = 0.0
        buffering = 0.0
        for st in self._transforms:
            native = st.processor.native_sample_rate
            algo += (st.processor.latency_samples + st.resampler_delay_native) / native
            buffering += (st.processor.native_frame_size - 1) / native
        if self._out_resampler:
            algo += self._out_resampler.delay_seconds
        return LatencyReport(algorithmic_ms=algo * 1000.0, buffering_ms=buffering * 1000.0)

    def process(self, chunk: Float32Array) -> Float32Array:
        """Process a planar ``(channels, n)`` float32 chunk at the pipeline rate."""
        if chunk.ndim != 2 or chunk.shape[0] != self.channels:
            raise AudioFormatError(f"expected shape ({self.channels}, n), got {chunk.shape}")
        self.samples_in += chunk.shape[1]
        x = chunk
        for st in self._transforms:
            x = st.run(x)
        if self._out_resampler:
            x = self._out_resampler.process(x)
        if self._analysis and x.shape[1]:
            mono = downmix_mono(x)
            for st in self._analysis:
                before = st.frames_done
                st.run(mono)
                self._collect(st, before)
        self.samples_out += x.shape[1]
        return x

    def flush(self) -> Float32Array:
        """Feed silence to push all buffered and delayed audio out of the pipeline."""
        lat = self.latency
        pad = int(np.ceil(lat.total_ms * self.sample_rate / 1000.0)) + 1
        for st in self._transforms:  # extra frame per stage covers rounding at each rate
            pad += int(
                np.ceil(
                    st.processor.native_frame_size
                    * self.sample_rate
                    / st.processor.native_sample_rate
                )
            )
        before_in = self.samples_in
        out = self.process(np.zeros((self.channels, pad), dtype=np.float32))
        self.samples_in = before_in
        return out

    def pop_results(self) -> list[AnalysisResult]:
        """Return and clear analysis results gathered since the last call."""
        res, self._results = self._results, []
        return res

    def reset(self) -> None:
        for st in self._transforms + self._analysis:
            st.reset()
        if self._out_resampler:
            self._out_resampler.reset()
        self._results.clear()
        self.samples_in = self.samples_out = 0

    def close(self) -> None:
        for proc in self.processors:
            proc.close()

    def _collect(self, st: _Stage, frames_before: int) -> None:
        values = st.processor.pop_results()
        native = st.processor.native_sample_rate
        fs = st.processor.native_frame_size
        for offset, vals in enumerate(values):
            start_native = (frames_before + offset) * fs - st.resampler_delay_native
            start = round(max(start_native, 0.0) * self.sample_rate / native)
            self._results.append(AnalysisResult(st.processor.name, start, vals))
