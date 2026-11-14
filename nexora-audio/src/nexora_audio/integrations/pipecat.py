"""Pipecat audio filter: nexora-audio as the input filter of a Pipecat transport.

This is how Dograh (and any Pipecat app) uses nexora-audio::

    from nexora_audio.integrations.pipecat import NexoraAudioFilter

    transport = FastAPIWebsocketTransport(
        websocket,
        FastAPIWebsocketParams(audio_in_filter=NexoraAudioFilter(), ...),
    )

One filter instance per call: it holds that call's DSP state. Pipecat calls ``start``
with the transport's sample rate, then ``filter`` with 16-bit mono PCM chunks. The filter
runs a :class:`~nexora_audio.streaming.session.StreamSession` (noise removal, speech
guard, loss concealment, voice enhancement; no turn events, because Pipecat has its own
VAD and turn logic) in a worker thread, so the event loop stays free for other calls.
Output keeps pace with input; the first chunks are shorter by the processing delay.

Install with ``pip install "nexora-audio[pipecat]"``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from pipecat.audio.filters.base_audio_filter import BaseAudioFilter
from pipecat.frames.frames import FilterControlFrame, FilterEnableFrame

from nexora_audio.streaming.codecs import AudioFormat
from nexora_audio.streaming.session import StreamSession

log = logging.getLogger("nexora_audio.pipecat")


class NexoraAudioFilter(BaseAudioFilter):
    """Pipecat ``BaseAudioFilter`` backed by nexora-audio.

    Args:
        offload: Process in a worker thread (default) instead of on the event loop.
        **settings: :class:`~nexora_audio.config.NexoraConfig` settings, e.g.
            ``noise_backend="rnnoise"`` for higher call density.
    """

    def __init__(self, *, offload: bool = True, **settings: Any) -> None:
        self._settings = settings
        self._offload = offload
        self._session: StreamSession | None = None
        self._enabled = True
        self.sample_rate = 0

    async def start(self, sample_rate: int) -> None:
        self.sample_rate = sample_rate
        fmt = AudioFormat("pcm16", sample_rate, 1)
        self._session = await asyncio.to_thread(
            StreamSession, input_format=fmt, turns=None, **self._settings
        )
        log.info("nexora-audio filter started", extra={"backends": self._session.backends})

    async def stop(self) -> None:
        if self._session is None:
            return
        log.info("nexora-audio call quality", extra={"quality": self._session.quality()})
        self._session.close()
        self._session = None

    async def process_frame(self, frame: FilterControlFrame) -> None:
        if isinstance(frame, FilterEnableFrame) and frame.enable != self._enabled:
            self._enabled = frame.enable
            if self._session is not None:
                # audio buffered before the toggle no longer lines up with what follows
                self._session.reset()

    async def filter(self, audio: bytes) -> bytes:
        if not self._enabled or self._session is None or not audio:
            return audio
        if self._offload:
            out = await self._session.aprocess(audio)
        else:
            out = self._session.process(audio)
        return out.audio

    def push_reference(self, audio: bytes) -> None:
        """Agent audio (16-bit mono PCM at the transport rate) just sent to the caller.

        Pipecat input filters do not see output audio, so call this from a frame processor
        on the output side (e.g. on ``OutputAudioRawFrame``). With a reference, the agent's
        own voice coming back is recognised; with ``echo_cancellation=True`` it is also
        removed from the caller's audio."""
        if self._session is not None and audio:
            self._session.push_reference(audio)

    def quality(self) -> dict[str, Any]:
        """Live quality numbers for this call (empty before ``start``)."""
        return self._session.quality() if self._session is not None else {}
