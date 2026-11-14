"""T5, the P0 exit test: a Dograh call with the `nexora` engine (AC-6).

The call goes through Dograh's real Twilio entry point:
``api.services.telephony.providers.twilio.transport.create_transport`` builds the
FastAPI WebSocket transport, Twilio serializer and ``audio_in_filter`` from the agent's
``noise_reduction`` setting. Only the database lookup of Twilio credentials is stubbed.
A fake WebSocket plays Twilio "media" events (8 kHz mu-law) of noisy speech; a stub STT
records the audio the transport hands downstream; a stub LLM sits behind it; the call is
ended with an EndFrame, the way Dograh's engine ends calls.
"""

import asyncio
import base64
import json
import wave
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest
from pipecat.audio.utils import create_stream_resampler, pcm_to_ulaw
from pipecat.frames.frames import EndFrame, Frame, InputAudioRawFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.tests import MockLLMService
from scipy.signal import resample_poly
from starlette.websockets import WebSocketState

from api.constants import APP_ROOT_DIR
from api.services.pipecat.audio_config import create_audio_config
from api.services.pipecat.noise_reduction.safe_filter import SafeAudioFilter
from api.services.telephony.providers.twilio import transport as twilio_transport

RATE = 8000
CHUNK = RATE // 50  # Twilio sends 20 ms media frames
SPEECH_WAV = APP_ROOT_DIR.parent / "pipecat/scripts/provider-watch/assets/speech-16k.wav"
NEXORA = {"enabled": True, "engine": "nexora"}


def db(ratio: float) -> float:
    return 20 * np.log10(max(ratio, 1e-12))


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x.astype(np.float64) ** 2))) if len(x) else 0.0


def call_audio() -> tuple[np.ndarray, slice, slice]:
    """1.5 s noise, then speech over noise (about 10 dB SNR), then 1 s noise."""
    with wave.open(str(SPEECH_WAV)) as wav:
        speech16 = np.frombuffer(wav.readframes(wav.getnframes()), dtype=np.int16)
    speech = resample_poly(speech16.astype(np.float64), RATE, 16000)
    lead, tail = int(1.5 * RATE), RATE
    clean = np.concatenate([np.zeros(lead), speech, np.zeros(tail)])
    rng = np.random.default_rng(7)
    noise = rng.standard_normal(len(clean))
    noise *= rms(speech) / rms(noise) / 10 ** (10 / 20)
    noisy = np.clip(clean + noise, -32768, 32767).astype(np.int16)
    return noisy, slice(lead, lead + len(speech)), slice(len(clean) - tail, len(clean))


class FakeTwilioSocket:
    """Plays Twilio media-stream events, then disconnects when told to."""

    def __init__(self, events: list[dict]):
        self.headers = {}
        self.client_state = WebSocketState.CONNECTED
        self.application_state = WebSocketState.CONNECTED
        self.sent: list[str | bytes] = []
        self._queue: asyncio.Queue = asyncio.Queue()
        for event in events:
            self._queue.put_nowait({"type": "websocket.receive", "text": json.dumps(event)})
        self.played = asyncio.Event()

    async def receive(self):
        if self._queue.empty():
            self.played.set()
        message = await self._queue.get()
        if '"media"' in message.get("text", ""):
            await asyncio.sleep(CHUNK / RATE)  # real time, as Twilio streams it
        return message

    def hang_up(self):
        self._queue.put_nowait({"type": "websocket.disconnect"})

    async def send_text(self, data: str):
        self.sent.append(data)

    async def send_bytes(self, data: bytes):
        self.sent.append(data)

    async def close(self, *args, **kwargs):
        self.client_state = WebSocketState.DISCONNECTED
        self.application_state = WebSocketState.DISCONNECTED


async def twilio_events(audio: np.ndarray) -> list[dict]:
    resampler = create_stream_resampler()
    events = [
        {"event": "connected", "protocol": "Call", "version": "1.0.0"},
        {"event": "start", "streamSid": "MZtest", "start": {"callSid": "CAtest", "streamSid": "MZtest",
                                                             "mediaFormat": {"encoding": "audio/x-mulaw",
                                                                             "sampleRate": RATE, "channels": 1}}},
    ]
    for i in range(0, len(audio) - CHUNK + 1, CHUNK):
        ulaw = await pcm_to_ulaw(audio[i : i + CHUNK].tobytes(), RATE, RATE, resampler)
        events.append({"event": "media", "streamSid": "MZtest",
                       "media": {"track": "inbound", "chunk": str(i // CHUNK), "payload": base64.b64encode(ulaw).decode()}})
    return events


class RecordingSTT(FrameProcessor):
    """Stub speech-to-text: records the caller audio it receives."""

    def __init__(self):
        super().__init__(name="RecordingSTT")
        self.audio = bytearray()
        self.sample_rates: set[int] = set()

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, InputAudioRawFrame):
            self.audio.extend(frame.audio)
            self.sample_rates.add(frame.sample_rate)
        await self.push_frame(frame, direction)


class RecordingHangup:
    """Stands in for Twilio's REST hangup (an external call): records that it was asked."""

    def __init__(self):
        self.calls = 0

    async def execute_hangup(self, *args, **kwargs):
        self.calls += 1
        return True


async def run_call(noise_reduction: dict):
    audio, speech_part, noise_part = call_audio()
    socket = FakeTwilioSocket(await twilio_events(audio))
    hangup = RecordingHangup()
    with patch.object(twilio_transport, "load_credentials_for_transport",
                      AsyncMock(return_value={"account_sid": "ACtest", "auth_token": "test"})), \
         patch.object(twilio_transport, "TwilioHangupStrategy", lambda: hangup):
        transport = await twilio_transport.create_transport(
            socket, workflow_run_id=1, audio_config=create_audio_config("twilio"), organization_id=1,
            noise_reduction_config=noise_reduction, stream_sid="MZtest", call_sid="CAtest",
        )
    stt = RecordingSTT()
    pipeline = Pipeline([transport.input(), stt, MockLLMService(), transport.output()])
    worker = PipelineWorker(pipeline, params=PipelineParams(audio_in_sample_rate=RATE, audio_out_sample_rate=RATE))

    async def end_after_audio():
        await socket.played.wait()
        await asyncio.sleep(0.5)  # let the last frames drain
        await worker.queue_frame(EndFrame())

    ender = asyncio.create_task(end_after_audio())
    async with asyncio.timeout(90):
        await PipelineRunner(handle_sigint=False).run(worker)
    await ender
    received = np.frombuffer(bytes(stt.audio), dtype=np.int16)
    transport.hangup = hangup
    return transport, stt, audio, received, speech_part, noise_part


@pytest.fixture(scope="module")
def nexora_call():
    return asyncio.run(run_call(NEXORA))


def test_call_pipeline_cleans_audio_before_stt(nexora_call):
    transport, stt, sent, received, speech_part, noise_part = nexora_call
    from nexora_audio.integrations.pipecat import NexoraAudioFilter

    filt = transport._params.audio_in_filter  # noqa: SLF001 - what Dograh built for this call
    assert isinstance(filt, SafeAudioFilter) and isinstance(filt._engine, NexoraAudioFilter)  # noqa: SLF001
    assert stt.sample_rates == {RATE}
    assert len(sent) - len(received) <= RATE // 5, "audio lost on the way to STT"

    noise_in, noise_out = rms(sent[noise_part]), rms(received[noise_part.start - RATE // 10 : noise_part.stop - RATE // 10])
    assert db(noise_out / noise_in) <= -10, f"noise at STT only {db(noise_out / noise_in):+.1f} dB"

    clean_speech_rms = rms(sent[speech_part])  # noisy speech level, 10 dB SNR
    speech_out = rms(received[speech_part])
    assert abs(db(speech_out / clean_speech_rms)) <= 3, f"speech level at STT {db(speech_out / clean_speech_rms):+.1f} dB"


def test_safe_filter_never_trips_during_call(nexora_call):
    transport = nexora_call[0]
    filt = transport._params.audio_in_filter  # noqa: SLF001
    assert filt.disabled_reason is None, filt.disabled_reason
    assert filt._frames > 100  # noqa: SLF001 - it really processed the call


def test_call_ends_normally(nexora_call):
    transport = nexora_call[0]
    filt = transport._params.audio_in_filter  # noqa: SLF001
    assert not filt.active  # stopped by the transport at the end of the call
    assert transport.hangup.calls == 1  # Dograh hung up the phone leg once


def test_without_noise_reduction_stt_hears_the_noise():
    """Control: with Dograh's default (noise reduction off) the noise reaches STT."""
    transport, _, sent, received, _, noise_part = asyncio.run(run_call({"enabled": False}))
    assert transport._params.audio_in_filter is None  # noqa: SLF001
    assert abs(db(rms(received[noise_part]) / rms(sent[noise_part]))) <= 1.5
