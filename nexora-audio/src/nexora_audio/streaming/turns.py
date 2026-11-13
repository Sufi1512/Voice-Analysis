"""Conversation turn tracking from voice-activity probabilities.

Turns VAD probabilities (one every 32 ms) into the events a voice agent needs:

* ``speech_start``: the user started talking
* ``speech_end``: the user stopped (after ``speech_end_ms`` of silence)
* ``end_of_turn``: the user has likely finished their turn (``end_of_turn_ms`` of
  silence after at least ``min_turn_ms`` of speech). Send the transcript to the LLM here.
* ``interruption``: while the agent is speaking, the user kept talking for
  ``interruption_min_ms``. Stop TTS playback here.
* ``backchannel``: while the agent is speaking, the user said something shorter than
  ``interruption_min_ms`` ("uh-huh", "yeah"). Usually ignore it and keep talking.

This is rule-based (duration and silence timing on top of Silero VAD). It is not a
learned end-of-turn or interruption model, so it cannot hear that a sentence is
unfinished, or tell a short "stop!" from a short "yeah". Tune the timings for your agent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

EventType = Literal["speech_start", "speech_end", "end_of_turn", "interruption", "backchannel"]


@dataclass(frozen=True, slots=True)
class TurnEvent:
    type: EventType
    time_ms: float  # position in the session's audio stream
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "time_ms": round(self.time_ms, 1), **self.data}


@dataclass(frozen=True, slots=True)
class TurnConfig:
    speech_threshold: float = 0.5
    silence_threshold: float = 0.35
    min_speech_ms: float = 64.0  # ignore blips shorter than two VAD windows
    speech_end_ms: float = 300.0
    end_of_turn_ms: float = 700.0
    min_turn_ms: float = 200.0
    interruption_min_ms: float = 400.0


class TurnTracker:
    """State machine fed with ``(time_ms, probability)`` for each VAD window."""

    def __init__(self, config: TurnConfig | None = None, window_ms: float = 32.0) -> None:
        self.config = config or TurnConfig()
        self.window_ms = window_ms
        self.agent_speaking = False
        self.reset()

    def reset(self) -> None:
        self.in_speech = False
        self._candidate_start: float | None = None
        self._speech_start = 0.0
        self._last_voice = 0.0
        self._turn_speech_ms = 0.0
        self._turn_open = False
        self._interrupted = False

    def set_agent_speaking(self, speaking: bool, time_ms: float = 0.0) -> None:
        self.agent_speaking = speaking
        if not speaking:
            self._interrupted = False

    def update(self, time_ms: float, probability: float) -> list[TurnEvent]:
        c = self.config
        events: list[TurnEvent] = []
        end_ms = time_ms + self.window_ms
        if probability >= c.speech_threshold:
            self._last_voice = end_ms
            if not self.in_speech:
                if self._candidate_start is None:
                    self._candidate_start = time_ms
                if end_ms - self._candidate_start >= c.min_speech_ms:
                    self.in_speech = True
                    self._speech_start = self._candidate_start
                    self._turn_open = True
                    events.append(TurnEvent("speech_start", self._speech_start))
            if (
                self.in_speech
                and self.agent_speaking
                and not self._interrupted
                and end_ms - self._speech_start >= c.interruption_min_ms
            ):
                self._interrupted = True
                events.append(
                    TurnEvent("interruption", end_ms, {"speech_ms": end_ms - self._speech_start})
                )
        elif probability < c.silence_threshold:
            self._candidate_start = None
            silence = end_ms - self._last_voice
            if self.in_speech and silence >= c.speech_end_ms:
                self.in_speech = False
                duration = self._last_voice - self._speech_start
                self._turn_speech_ms += duration
                events.append(TurnEvent("speech_end", self._last_voice, {"speech_ms": duration}))
                if self.agent_speaking and not self._interrupted:
                    events.append(
                        TurnEvent("backchannel", self._last_voice, {"speech_ms": duration})
                    )
                    self._turn_speech_ms -= duration  # a backchannel is not a user turn
            if (
                self._turn_open
                and not self.in_speech
                and silence >= c.end_of_turn_ms
                and self._turn_speech_ms >= c.min_turn_ms
            ):
                events.append(
                    TurnEvent(
                        "end_of_turn",
                        end_ms,
                        {"speech_ms": self._turn_speech_ms, "silence_ms": silence},
                    )
                )
                self._turn_open = False
                self._turn_speech_ms = 0.0
            elif self._turn_open and not self.in_speech and silence >= c.end_of_turn_ms:
                # too little speech for a turn (e.g. only backchannels): drop it quietly
                self._turn_open = False
                self._turn_speech_ms = 0.0
        else:
            # between thresholds: keeps the current state, counts as neither
            if not self.in_speech:
                self._candidate_start = None
        return events
