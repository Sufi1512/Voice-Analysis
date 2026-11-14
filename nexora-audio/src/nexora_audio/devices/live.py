"""Live microphone and speaker streaming through a ``StreamSession``.

One full-duplex sound-card stream (PortAudio via ``sounddevice``) moves audio in fixed blocks.
Its callback only copies: microphone samples into a ring buffer, and the next speaker
samples out of another. A worker thread takes the microphone audio in 20 ms chunks, runs the
session, and hands back the cleaned audio and the turn events.

Two uses:

- ``monitor=True``: you hear your own cleaned voice (a quick demo of noise removal).
- ``monitor=False``: the speaker plays what you ``play()`` (your agent's voice). That audio
  is also given to the session as the echo reference, sample-aligned with the microphone,
  so the agent's own voice coming back is not taken for the caller.

Dropouts are counted: ``input_overflows`` (the worker fell behind and microphone audio was
lost), ``output_underruns`` (nothing ready to play in time) and the sound card's own flags.
"""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np

from nexora_audio.devices.ring import RingBuffer
from nexora_audio.streaming.codecs import AudioFormat
from nexora_audio.streaming.session import StreamSession
from nexora_audio.streaming.turns import TurnEvent
from nexora_audio.utils.audio_utils import Float32Array


class DuplexStream(Protocol):
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def close(self) -> None: ...


Callback = Callable[[Float32Array, Float32Array, int, Any], None]
StreamFactory = Callable[..., DuplexStream]


def sounddevice_stream(
    *, samplerate: int, blocksize: int, device: Any, callback: Callback
) -> DuplexStream:
    """The real sound card (needs ``pip install nexora-audio[devices]``; on Linux also the
    system PortAudio library, ``libportaudio2``)."""
    import sounddevice as sd

    def cb(indata: Any, outdata: Any, frames: int, _time: Any, status: Any) -> None:
        callback(indata[:, 0], outdata[:, 0], frames, status)

    stream: DuplexStream = sd.Stream(
        samplerate=samplerate,
        blocksize=blocksize,
        device=device,
        channels=1,
        dtype="float32",
        latency="low",
        callback=cb,
    )
    return stream


def list_devices() -> list[dict[str, Any]]:
    """Sound devices PortAudio can see: index, name, input/output channels, default rate."""
    import sounddevice as sd

    out = []
    for i, d in enumerate(sd.query_devices()):
        out.append(
            {
                "index": i,
                "name": d["name"],
                "inputs": d["max_input_channels"],
                "outputs": d["max_output_channels"],
                "default_rate": d["default_samplerate"],
            }
        )
    return out


@dataclass
class LiveStats:
    blocks: int = 0
    chunks: int = 0
    input_overflows: int = 0  # microphone samples lost: the worker fell behind
    output_underruns: int = 0  # blocks with nothing (or too little) to play
    device_flags: int = 0  # PortAudio's own input-overflow / output-underflow reports
    worst_chunk_ms: float = 0.0
    events: dict[str, int] = field(default_factory=dict)

    def dropouts(self) -> int:
        return self.input_overflows + self.output_underruns + self.device_flags


class LiveSession:
    """Microphone -> StreamSession -> speaker or your code, in real time."""

    def __init__(
        self,
        *,
        sample_rate: int = 16000,
        block_ms: float = 10.0,
        chunk_ms: float = 20.0,
        monitor: bool = True,
        device: Any = None,
        prefill_ms: float = 40.0,
        stream_factory: StreamFactory = sounddevice_stream,
        on_event: Callable[[TurnEvent], None] | None = None,
        **session_settings: Any,
    ) -> None:
        self.rate = sample_rate
        self.block = round(sample_rate * block_ms / 1000)
        self.chunk = round(sample_rate * chunk_ms / 1000)
        self.monitor = monitor
        self.on_event = on_event
        self.stats = LiveStats()
        fmt = AudioFormat("float32", sample_rate)
        self._fmt = fmt
        session_settings.setdefault("judge_in_background", True)
        self.session = StreamSession(input_format=fmt, **session_settings)
        self._warm_up()
        cap = sample_rate * 2  # 2 s of headroom each way
        self._mic = RingBuffer(cap)
        self._ref = RingBuffer(cap)  # what the speaker played, aligned with the mic
        self._out = RingBuffer(cap)  # what the speaker plays next
        self._prefill = round(sample_rate * prefill_ms / 1000)
        self._out.write(np.zeros(self._prefill, np.float32))
        self._clean: queue.Queue[Float32Array] = queue.Queue(maxsize=500)
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._worker = threading.Thread(target=self._work, name="nexora-live", daemon=True)
        self._stream = stream_factory(
            samplerate=sample_rate, blocksize=self.block, device=device, callback=self._callback
        )
        self._running = False

    def _warm_up(self) -> None:
        """Run the models once before the sound card starts (first calls are slow)."""
        silence = np.zeros(self.rate, np.float32).tobytes()
        self.session.process(silence)
        if self.session._turns is not None and self.session._turns.judge is not None:
            from nexora_audio.backends import smart_turn

            smart_turn.complete_probability(np.zeros(smart_turn.MODEL_RATE, np.float32))
        self.session.reset()

    # -- sound-card thread: copy only -------------------------------------------------

    def _callback(
        self, indata: Float32Array, outdata: Float32Array, frames: int, status: Any
    ) -> None:
        self.stats.blocks += 1
        if status:
            self.stats.device_flags += 1
        played = self._out.read(frames)
        if played is None:
            self.stats.output_underruns += 1
            played = np.zeros(frames, np.float32)
        outdata[:] = played
        if self._mic.write(indata) < frames:
            self.stats.input_overflows += 1
        self._ref.write(played)
        self._wake.set()

    # -- worker thread --------------------------------------------------------------------

    def _work(self) -> None:
        while not self._stop.is_set():
            mic = self._mic.read(self.chunk)
            if mic is None:
                self._wake.wait(0.05)
                self._wake.clear()
                continue
            ref = self._ref.read(self.chunk)
            t0 = time.perf_counter()
            if not self.monitor and ref is not None:
                self.session.push_reference(ref.tobytes(), self._fmt)
            res = self.session.process(mic.tobytes())
            ms = (time.perf_counter() - t0) * 1000
            self.stats.chunks += 1
            self.stats.worst_chunk_ms = max(self.stats.worst_chunk_ms, ms)
            clean = np.frombuffer(res.audio, np.float32)
            if self.monitor:
                self._out.write(clean)
            else:
                try:
                    self._clean.put_nowait(clean)
                except queue.Full:  # nobody is reading processed_audio(): drop the oldest
                    self._clean.get_nowait()
                    self._clean.put_nowait(clean)
            for ev in res.events:
                self.stats.events[ev.type] = self.stats.events.get(ev.type, 0) + 1
                if self.on_event is not None:
                    self.on_event(ev)

    # -- public ---------------------------------------------------------------------------

    def play(self, audio: Float32Array) -> int:
        """Queue agent audio for the speaker (``monitor=False``); also the echo reference."""
        return self._out.write(np.asarray(audio, np.float32))

    def processed_audio(self, timeout: float = 1.0) -> Iterator[Float32Array]:
        """Cleaned microphone audio, chunk by chunk (``monitor=False``)."""
        while self._running:
            try:
                yield self._clean.get(timeout=timeout)
            except queue.Empty:
                continue

    def start(self) -> LiveSession:
        self._running = True
        self._worker.start()
        self._stream.start()
        return self

    def stop(self) -> LiveStats:
        if not self._running:
            return self.stats
        self._running = False
        self._stream.stop()
        self._stream.close()
        self._stop.set()
        self._wake.set()
        self._worker.join(5)
        self.session.close()
        return self.stats

    def __enter__(self) -> LiveSession:
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.stop()
