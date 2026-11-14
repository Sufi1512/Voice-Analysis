"""Per-connection streaming sessions for servers (WebSocket, SIP, WebRTC gateways).

One :class:`StreamSession` per caller/connection. Feed it raw bytes as they arrive;
it returns cleaned bytes plus conversation events. Sessions are independent and can
run concurrently in threads: the native backends release the GIL while processing.

Example (asyncio)::

    session = StreamSession(input_format=AudioFormat("pcm16", 16000))
    async for message in websocket:
        out = await session.aprocess(message)
        await agent.send_audio(out.audio)
        for event in out.events:
            await agent.send_event(event.to_dict())
"""

from __future__ import annotations

import asyncio
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from math import gcd
from types import TracebackType
from typing import Any, Self

import numpy as np
from pydantic import ValidationError
from scipy.signal import resample_poly

from nexora_audio.backends import smart_turn
from nexora_audio.backends.aec3 import AEC3Processor
from nexora_audio.client import NexoraAudio
from nexora_audio.config import NexoraConfig
from nexora_audio.core.capabilities import BackendRegistry
from nexora_audio.core.resampler import StreamingResampler
from nexora_audio.exceptions import ConfigurationError
from nexora_audio.streaming.codecs import SILENCE_LEVEL, AudioFormat, StreamDecoder, encode
from nexora_audio.streaming.echo import EchoGate, ReferenceTimeline
from nexora_audio.streaming.plc import LossConcealer
from nexora_audio.streaming.quality import QualityMonitor
from nexora_audio.streaming.turns import TurnConfig, TurnEvent, TurnTracker
from nexora_audio.utils.audio_utils import Float32Array
from nexora_audio.utils.metrics import TimingStats

RING_S = 10.0  # Smart Turn looks at the last 8 s


@dataclass(frozen=True, slots=True)
class SessionOutput:
    audio: bytes
    events: list[TurnEvent] = field(default_factory=list)


class StreamSession:
    """Cleans one audio stream and tracks conversation turns.

    Args:
        config: Processing settings (``sample_rate`` and ``channels`` are taken from
            ``input_format``). Keyword settings can be used instead.
        input_format: Wire format of incoming bytes.
        output_format: Wire format of returned bytes (default: same as input; PCM16 at
            the same rate when the input is Opus).
        turns: Turn/interruption settings, or ``None`` to disable turn events.
        loss_concealment: Conceal lost packets that arrive as digital silence, and enable
            :meth:`conceal` (mono streams).
        judge_in_background: Run the Smart Turn model on its own thread so ``process()``
            never waits ~45 ms for it at a pause (use for live audio; the default keeps
            results independent of timing).
    """

    def __init__(
        self,
        config: NexoraConfig | None = None,
        *,
        input_format: AudioFormat | None = None,
        output_format: AudioFormat | None = None,
        turns: TurnConfig | None = TurnConfig(),  # noqa: B008 - immutable dataclass
        loss_concealment: bool = True,
        registry: BackendRegistry | None = None,
        judge_in_background: bool = False,
        **settings: Any,
    ) -> None:
        self.input_format = input_format or AudioFormat()
        # Smart Turn takes ~45 ms per pause; real-time callers run it on its own thread so
        # process() never stalls (the verdict is used when ready). Offline use keeps it
        # synchronous, so results do not depend on timing.
        self._judge_pool = (
            ThreadPoolExecutor(1, thread_name_prefix="nexora-turn") if judge_in_background else None
        )
        default_out = (
            AudioFormat("pcm16", self.input_format.sample_rate, self.input_format.channels)
            if self.input_format.packetized
            else self.input_format
        )
        self.output_format = output_format or default_out
        if self.output_format.packetized:
            raise ConfigurationError("Opus output is not supported: use pcm16, float32 or G.711")
        if self.output_format.channels != self.input_format.channels:
            raise ConfigurationError("input and output must have the same channel count")
        if config is not None and settings:
            raise ConfigurationError("pass either a NexoraConfig or keyword settings, not both")
        updates: dict[str, Any] = {
            "sample_rate": self.input_format.sample_rate,
            "channels": self.input_format.channels,
        }
        if turns is not None:
            updates["vad"] = True
        try:
            base = config.model_dump() if config is not None else settings
            cfg = NexoraConfig(**{**base, **updates})
        except ValidationError as exc:
            raise ConfigurationError(str(exc)) from exc
        self._audio = NexoraAudio(cfg, registry=registry)
        self._audio.initialize()
        self._pipeline = self._audio._require_pipeline()
        self._decoder = StreamDecoder(self.input_format)
        rin, rout = self.input_format.sample_rate, self.output_format.sample_rate
        self._out_rs = (
            StreamingResampler(rin, rout, self.input_format.channels) if rin != rout else None
        )
        self._turns = TurnTracker(turns) if turns is not None else None
        # processed caller audio (mono, input rate) for the Smart Turn judge
        self._ring = np.zeros(0, np.float32)
        self._ring_end = 0  # output samples produced so far
        self._ring_keep = int(RING_S * self.input_format.sample_rate)
        if self._turns is not None and turns is not None and turns.smart_turn:
            self._turns.judge = self._judge if smart_turn.probe() is None else None
        rate = self.input_format.sample_rate
        self._plc = (
            LossConcealer(rate, SILENCE_LEVEL[self.input_format.encoding])
            if loss_concealment and self.input_format.channels == 1
            else None
        )
        self._monitor = QualityMonitor(rate)
        # echo: the agent audio sent to the caller, on the caller-audio timeline
        self._pos = 0  # caller-audio samples received (incl. concealed)
        self._timeline = ReferenceTimeline(rate)
        self._gate = EchoGate(rate)
        self._hop = self._gate.hop
        self._hop_buf = np.zeros(0, np.float32)
        self._ref_decoders: dict[AudioFormat, StreamDecoder] = {}
        self._ref_resamplers: dict[tuple[int, int], StreamingResampler] = {}
        self._aec: AEC3Processor | None = next(
            (p for p in self._pipeline.processors if isinstance(p, AEC3Processor)), None
        )
        self._agent_auto = False
        self._lock = threading.Lock()
        self._latency_ms = self._pipeline.latency.algorithmic_ms
        self.timing = TimingStats()
        """Processing time per :meth:`process` call."""
        self.closed = False

    # -- properties ---------------------------------------------------------------

    @property
    def config(self) -> NexoraConfig:
        return self._audio.config

    @property
    def backends(self) -> list[str]:
        return self._audio.backends

    @property
    def latency_ms(self) -> float:
        """Delay the session adds to the audio (algorithmic, excludes buffering)."""
        extra = self._out_rs.delay_seconds * 1000 if self._out_rs else 0.0
        return self._latency_ms + extra

    @property
    def user_speaking(self) -> bool:
        return bool(self._turns and self._turns.in_speech)

    # -- processing ---------------------------------------------------------------

    def process(self, data: bytes) -> SessionOutput:
        """Process the next bytes of the stream (any length; partial samples are kept)."""
        with self._lock:
            self._check_open()
            t0 = time.perf_counter()
            planar = self._decoder.decode(data)
            if planar.shape[1]:
                self._monitor.update(planar[0])
                if self._plc is not None:
                    planar = self._plc.process(planar[0])[None, :]
            return self._run(planar, t0)

    def push_reference(self, data: bytes, fmt: AudioFormat | None = None) -> None:
        """Agent audio just sent to the caller (default format: this session's output).

        Enables echo-aware turn events (the agent's own voice coming back is not reported
        as the caller speaking or interrupting) and, when ``echo_cancellation=True``, feeds
        the echo canceller. While reference audio is still playing, the session treats the
        agent as speaking (audible agent audio in the last 300 ms); :meth:`set_agent_speaking`
        is then not needed.
        """
        fmt = fmt or self.output_format
        with self._lock:
            self._check_open()
            dec = self._ref_decoders.get(fmt)
            if dec is None:
                dec = self._ref_decoders[fmt] = StreamDecoder(fmt)
            x = dec.decode(data)
            if not x.shape[1]:
                return
            mono = x.mean(axis=0) if x.shape[0] > 1 else x[0]
            mono = self._resample(mono, fmt.sample_rate, self.input_format.sample_rate)
            self._timeline.push(mono, self._pos)
            self._agent_auto = True
            if self._aec is not None:
                rate = self._aec.native_sample_rate
                self._aec.push_reference(
                    self._resample(mono, self.input_format.sample_rate, rate, "aec")
                )

    def _resample(self, x: Float32Array, src: int, dst: int, tag: str = "ref") -> Float32Array:
        if src == dst:
            return x
        key = (src, dst) if tag == "ref" else (-src, -dst)
        rs = self._ref_resamplers.get(key)
        if rs is None:
            rs = self._ref_resamplers[key] = StreamingResampler(src, dst, 1)
        out: Float32Array = rs.process(x[None, :])[0]
        return out

    def _track_echo(self, mono: Float32Array) -> None:
        """Feed the echo gate in 10 ms hops and follow whether the agent is still playing."""
        buf = np.concatenate([self._hop_buf, mono]) if len(self._hop_buf) else mono
        h = self._hop
        m = len(buf) // h
        start = self._pos - len(self._hop_buf)
        for i in range(m):
            seg = buf[i * h : (i + 1) * h]
            self._gate.update(seg, self._timeline.get(start + i * h, h))
        self._hop_buf = buf[m * h :].copy()
        self._pos += len(mono)
        if self._agent_auto and self._turns is not None:
            # the agent is speaking while its audio was audible in the last 300 ms
            win = int(0.3 * self.input_format.sample_rate)
            recent = self._timeline.get(self._pos - win, win)
            playing = float(np.mean(recent.astype(np.float64) ** 2)) > 1e-6  # -60 dBFS
            if playing != self._turns.agent_speaking:
                self._turns.set_agent_speaking(playing)

    def conceal(self, ms: float) -> SessionOutput:
        """The transport knows ``ms`` of audio is missing (and sent nothing for it):
        produce concealment audio for that span, so the output stays time-aligned."""
        with self._lock:
            self._check_open()
            t0 = time.perf_counter()
            n = round(ms * self.input_format.sample_rate / 1000)
            ch = self.input_format.channels
            if self._plc is not None:
                planar = self._plc.conceal(n)[None, :]
            else:
                planar = np.zeros((ch, n), np.float32)
            return self._run(planar, t0)

    def _run(self, planar: Float32Array, t0: float) -> SessionOutput:
        if planar.shape[1]:
            self._track_echo(planar.mean(axis=0) if planar.shape[0] > 1 else planar[0])
        out = self._pipeline.process(planar) if planar.shape[1] else planar
        self._remember(out)
        events = self._collect_events()
        audio = self._encode(out)
        self.timing.add(time.perf_counter() - t0)
        return SessionOutput(audio, events)

    @property
    def input_seconds(self) -> float:
        """Audio received so far, in seconds (decoded, so it also works for Opus)."""
        return self._monitor.samples / self.input_format.sample_rate

    def quality(self) -> dict[str, Any]:
        """Live quality numbers for this call (see :mod:`nexora_audio.streaming.quality`)."""
        q = self._monitor.summary()
        rate = self.input_format.sample_rate
        if self._plc is not None:
            q["concealed_ms"] = round(1000 * self._plc.concealed_samples / rate, 1)
            q["concealed_pct"] = (
                round(100 * self._plc.concealed_samples / self._monitor.samples, 2)
                if self._monitor.samples
                else 0.0
            )
            q["loss_events"] = self._plc.events
        guard = sum(
            getattr(p, "guard_restored_frames", 0)
            for p in getattr(self._pipeline, "processors", [])
        )
        q["guard_restored_frames"] = guard
        if self.timing.count:
            q["chunk_p50_ms"] = round(self.timing.p50_ms, 3)
            q["chunk_p99_ms"] = round(self.timing.p99_ms, 3)
        q["latency_ms"] = round(self.latency_ms, 2)
        if self._agent_auto:
            q["echo_delay_ms"] = (
                round(self._gate.delay_hops * 10.0, 1) if self._gate.delay_hops >= 0 else None
            )
            q["echo_windows_ignored"] = self._gate.echo_hops
        if self._aec is not None:
            q["aec"] = self._aec.stats()
        return q

    async def aprocess(self, data: bytes) -> SessionOutput:
        """Async version of :meth:`process`: runs in a worker thread so the event loop
        stays free. Await calls for one session in order."""
        return await asyncio.to_thread(self.process, data)

    def set_agent_speaking(self, speaking: bool) -> None:
        """Tell the session whether the agent is currently playing audio to the user.
        Enables ``interruption`` and ``backchannel`` events."""
        if self._turns is not None:
            self._turns.set_agent_speaking(speaking)

    def push_transcript(self, text: str) -> None:
        """The caller's latest (interim or final) speech-to-text for the current turn.

        If it ends on a word no sentence can end on ("...a lot of", "...because", "um"),
        the turn waits ``TurnConfig.incomplete_silence_ms`` before ``end_of_turn``. Send it
        as soon as your STT has it; text for a turn that already ended is ignored.
        """
        if self._turns is not None:
            with self._lock:
                self._turns.set_transcript(text)

    def flush(self) -> SessionOutput:
        """End of stream: return all buffered audio and remaining events."""
        with self._lock:
            self._check_open()
            out = self._pipeline.flush()
            self._remember(out)
            events = self._collect_events()
            if self._turns is not None:  # the stream is over: so is an open turn
                end_ms = 1000.0 * self._pos / self.input_format.sample_rate
                events += self._turns.finish(end_ms)
            audio = self._encode(out)
            if self._out_rs is not None:
                audio += encode(self._out_rs.flush(), self.output_format)
            return SessionOutput(audio, events)

    def reset(self) -> None:
        """Start a new, unrelated stream on the same session."""
        with self._lock:
            self._pipeline.reset()
            self._decoder.reset()
            if self._out_rs is not None:
                self._out_rs.reset()
            if self._turns is not None:
                self._turns.reset()
            if self._plc is not None:
                self._plc.reset()
            self._monitor.reset()
            self._timeline.reset()
            self._gate.reset()
            self._pos, self._agent_auto = 0, False
            self._ring, self._ring_end = np.zeros(0, np.float32), 0
            self._hop_buf = np.zeros(0, np.float32)
            self.timing.reset()

    def close(self) -> None:
        with self._lock:
            if not self.closed:
                self._audio.close()
                if self._judge_pool is not None:
                    self._judge_pool.shutdown(wait=False, cancel_futures=True)
                self.closed = True

    # -- context managers ---------------------------------------------------------

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self, et: type[BaseException] | None, e: BaseException | None, tb: TracebackType | None
    ) -> None:
        self.close()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self, et: type[BaseException] | None, e: BaseException | None, tb: TracebackType | None
    ) -> None:
        self.close()

    # -- internals ----------------------------------------------------------------

    def _check_open(self) -> None:
        if self.closed:
            raise ConfigurationError("session is closed")

    def _encode(self, planar: Float32Array) -> bytes:
        if self._out_rs is not None:
            planar = self._out_rs.process(planar)
        return encode(planar, self.output_format) if planar.shape[1] else b""

    def _remember(self, out: Float32Array) -> None:
        if self._turns is None or self._turns.judge is None or not out.shape[1]:
            return
        mono = out.mean(axis=0) if out.shape[0] > 1 else out[0]
        self._ring = np.concatenate([self._ring, mono.astype(np.float32)])[-self._ring_keep :]
        self._ring_end += out.shape[1]

    def _judge(self, start_ms: float, end_ms: float) -> float | Future[float | None] | None:
        """Smart Turn on the processed caller audio between two input-timeline times."""
        rate = self.input_format.sample_rate
        lat = self._latency_ms
        first = self._ring_end - len(self._ring)
        a = max(round((start_ms + lat) * rate / 1000), first)
        b = min(round((end_ms + lat) * rate / 1000), self._ring_end)
        if b - a < rate // 10:
            return None
        x = self._ring[a - first : b - first]
        if rate != smart_turn.MODEL_RATE:
            g = gcd(rate, smart_turn.MODEL_RATE)
            x = resample_poly(x, smart_turn.MODEL_RATE // g, rate // g).astype(np.float32)
        else:
            x = x.copy()  # the ring keeps changing; the background job needs its own copy
        if self._judge_pool is not None:
            return self._judge_pool.submit(smart_turn.complete_probability, x)
        return smart_turn.complete_probability(x)

    def _collect_events(self) -> list[TurnEvent]:
        results = self._pipeline.pop_results()
        if self._turns is None:
            return []
        rate = self.input_format.sample_rate
        events: list[TurnEvent] = []
        for r in results:
            if r.processor != "silero-vad":
                continue
            # VAD sees processed audio; shift times back onto the input timeline
            t_ms = r.start_sample * 1000.0 / rate - self._latency_ms
            p = float(r.values["probability"])
            # Silero windows are 32 ms
            agent = self._turns.agent_speaking
            if p >= 0.35 and self._agent_auto and self._gate.is_echo(t_ms / 1000, 0.032, agent):
                p = 0.0  # the agent's own voice coming back: not the caller speaking
            events.extend(self._turns.update(max(t_ms, 0.0), p))
        return events


def silence_bytes(fmt: AudioFormat, ms: float) -> bytes:
    """Encoded silence, handy for keep-alives and tests."""
    n = round(fmt.sample_rate * ms / 1000)
    return encode(np.zeros((fmt.channels, n), dtype=np.float32), fmt)
