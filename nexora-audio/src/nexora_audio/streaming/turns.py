"""Conversation turn tracking from voice-activity probabilities.

Turns VAD probabilities (one every 32 ms) into the events a voice agent needs:

* ``speech_start``: the user started talking
* ``speech_end``: the user stopped (after ``speech_end_ms`` of silence)
* ``end_of_turn``: the user has likely finished their turn. Send the transcript to the
  LLM here. With a *judge* (Smart Turn, see below) the tracker asks, at each pause, whether
  the turn sounds finished: if it does, the turn ends after ``complete_silence_ms``; if it
  sounds unfinished ("I'd like to book a flight to..."), it waits for
  ``incomplete_silence_ms`` of silence. Without a judge: ``end_of_turn_ms`` of silence.
  Either way at least ``min_turn_ms`` of speech is needed.
* ``interruption``: while the agent is speaking, the user kept talking for
  ``interruption_min_ms``. Stop TTS playback here.
* ``backchannel``: while the agent is speaking, the user said something shorter than
  ``interruption_min_ms`` ("uh-huh", "yeah"). Usually ignore it and keep talking.

Speech detection is Silero VAD; end-of-turn uses Smart Turn v3.2 when a judge is given
(``StreamSession`` does this by default). Interruption and backchannel are still rule
based: a short "stop!" and a short "yeah" look the same. Tune the timings for your agent.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

Judge = Callable[[float, float], float | None]
"""``judge(start_ms, end_ms)`` -> probability (0-1) that the turn in that span is finished,
or ``None`` if it cannot tell."""

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
    end_of_turn_ms: float = 700.0  # used when there is no judge (or it cannot tell)
    min_turn_ms: float = 200.0
    interruption_min_ms: float = 400.0
    smart_turn: bool = True  # let StreamSession judge pauses with Smart Turn v3.2
    smart_turn_threshold: float = 0.5
    # sounds finished: end the turn after this much silence. 700 ms (= end_of_turn_ms) means
    # Smart Turn never ends a turn sooner than the plain rule, it only waits longer when the
    # caller sounds unfinished. Lower it (300-500) for a snappier agent that cuts in more.
    complete_silence_ms: float = 700.0
    incomplete_silence_ms: float = 2000.0  # sounds unfinished: wait this long
    pre_speech_ms: float = 300.0  # audio before the turn's first word given to the judge


class TurnTracker:
    """State machine fed with ``(time_ms, probability)`` for each VAD window."""

    def __init__(
        self,
        config: TurnConfig | None = None,
        window_ms: float = 32.0,
        judge: Judge | None = None,
    ) -> None:
        self.config = config or TurnConfig()
        self.window_ms = window_ms
        self.judge = judge
        self.agent_speaking = False
        self.reset()

    def reset(self) -> None:
        self.in_speech = False
        self._candidate_start: float | None = None
        self._speech_start = 0.0
        self._last_voice = 0.0
        self._turn_speech_ms = 0.0
        self._turn_open = False
        self._turn_start = 0.0
        self._interrupted = False
        self._verdict: float | None = None

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
                    if not self._turn_open:
                        self._turn_start = self._speech_start
                    self._turn_open = True
                    self._verdict = None
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
                elif self.judge is not None and self._turn_speech_ms >= c.min_turn_ms:
                    try:
                        # up to the last voiced window: trailing silence makes the model
                        # call unfinished sentences finished (measured, see E5_SPEC.md)
                        self._verdict = self.judge(
                            max(self._turn_start - c.pre_speech_ms, 0.0), self._last_voice
                        )
                    except Exception:  # a broken judge must never stop turn-taking
                        self._verdict = None
            wait = self._wait_ms()
            if (
                self._turn_open
                and not self.in_speech
                and silence >= wait
                and self._turn_speech_ms >= c.min_turn_ms
            ):
                data: dict[str, Any] = {"speech_ms": self._turn_speech_ms, "silence_ms": silence}
                if self._verdict is not None:
                    data["complete_probability"] = round(self._verdict, 3)
                events.append(TurnEvent("end_of_turn", end_ms, data))
                self._turn_open = False
                self._turn_speech_ms = 0.0
                self._verdict = None
            elif self._turn_open and not self.in_speech and silence >= wait:
                # too little speech for a turn (e.g. only backchannels): drop it quietly
                self._turn_open = False
                self._turn_speech_ms = 0.0
                self._verdict = None
        else:
            # between thresholds: keeps the current state, counts as neither
            if not self.in_speech:
                self._candidate_start = None
        return events

    def _wait_ms(self) -> float:
        """Silence needed before the open turn ends."""
        c = self.config
        if self._verdict is None:
            return c.end_of_turn_ms
        if self._verdict >= c.smart_turn_threshold:
            return c.complete_silence_ms
        return c.incomplete_silence_ms
