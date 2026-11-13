# E4: echo (spec and results)

Phase E4 of `VOICE_QUALITY_PLAN.md`, approved by the user on 2026-11-13 ("Okey do it",
twice, including building the WebRTC library). Fixes F6 (acoustic echo), F7 (line echo)
and F8 (false barge-in from echo).

## What was wrong

Before E4, every speakerphone case in the quality lab made the agent think the caller had
interrupted, and the echo was not removed (0.2-2 dB). nexora-audio had the
`echo_cancellation` setting but no engine behind it, and the turn tracker knew *that* the
agent was speaking but not *what* it said.

## What E4 adds

1. **The agent's audio as a reference.** `StreamSession.push_reference(bytes)` takes the
   agent audio just sent to the caller and places it on the caller-audio timeline as a
   playout queue. While it is audible, the session marks the agent as speaking by itself.
   - nexora-server, Relay mode: done automatically from the audio the agent sends.
   - nexora-server, Process mode: `{"type": "agent_audio", "data": "<base64>"}`.
   - Pipecat/Dograh: `NexoraAudioFilter.push_reference()`. A Pipecat input filter cannot
     see output audio, so an output-side frame processor must call it. Not wired into
     Dograh yet.
2. **Echo-aware barge-in** (`streaming/echo.py`, always on once a reference is pushed).
   - **Learning the path.** It learns the echo path (delay 0-600 ms, level) from the
     envelopes of both streams. A path counts only above 0.7 correlation: real echo paths
     measure 0.83-0.92, chance matches with a headset at most 0.61. An "echo" quieter than
     the line's own noise floor is rejected too.
   - **Ignoring the echo.** Caller audio explained by the predicted echo (with a decaying
     tail) is not reported as speech or an interruption.
   - **First second.** Before the path is learned (the agent's first 0.4-1 s), speech
     while the agent is audible counts as possible echo.
   - **Headsets.** After 1.5 s of agent speech with no path, there is assumed to be no echo
     (a headset).
3. **Echo cancellation** (`backends/aec3.py`, `echo_cancellation=True`, off by default).
   - **The engine.** WebRTC AEC3 (Google, BSD-3), as in Chrome. We build it ourselves from
     the `webrtc-audio-processing` 2.1 crate's bundled source, with Abseil (Apache-2.0).
     It ships as `_native/linux-x86_64/libnexora_aec.so`; build recipe in
     `native/nexora-aec/`, provenance in `_native/PROVENANCE.md`. A small shim keeps it
     loadable on glibc 2.34+ (Ubuntu 22.04, Debian 12).
   - **Placement.** It runs first in the pipeline, before noise removal, at the stream's
     own rate.
   - **Two protections for the caller's voice:**
     - *Near-transparent suppressor tuning.* AEC3's defaults cut the caller by 20-48 dB
       while the agent talks, even with no echo.
     - *Headset bypass.* When there is no echo path, audio passes through untouched.

## Results (quality lab, 28 speakerphone cases, full profile)

The cases cover delays of 40/120/250/400 ms, and echo 6 dB louder than, equal to, and
10 dB quieter than the caller. They include headsets with no echo, and interruptions in
the agent's first second.

| | Before E4 | Reference only | Reference + canceller |
| --- | --- | --- | --- |
| False interruptions from echo (agent-only cases) | 12 of 12 | 2 | **0** |
| Real interruptions missed | 100% | 4 of 16 | 3 of 16 |
| Echo removed, median | 0.8 dB | 0.8 dB | **26.9 dB** |
| Echo removed, worst case | 0.2 dB | 0.1 dB | 14.4 dB |
| Caller speech cut while both talk, median | ~0% | 0% | 8.2% |
| Headset (no echo): caller speech cut | n/a | 0.3% | 0.3-0.5% |

**Still failing:**

- **Echo louder than the caller.** All 3 missed interruptions are cases where the echo is
  6 dB louder than the caller. No canceller can hear a caller under that without risking
  the agent's own voice.
- **Speech cut in the agent's first second.** While both talk there, the caller loses up
  to 42%, because the canceller has not adapted yet. The agent stops talking on an
  interruption, so the overlap is short.
- **Echo removal on our synthetic echo is about 27 dB, not 30.** That echo is harsher than
  most real devices: overdriven speaker, reverberant room.
- **Real recordings are still needed** to confirm all of this.

Server checks: `tests/test_streaming.py` shows the same echo stream causing a false
interruption without a reference, and none with `agent_audio`.

## Settings

| Setting | Default | Meaning |
| --- | --- | --- |
| `echo_cancellation` | `False` | Remove the agent's echo with AEC3 (needs a reference) |
| `push_reference(...)` | not called | Echo-aware turn events, and the canceller's reference |

Echo cancellation stays off by default. Without a reference it cannot work, and most
phone handsets already cancel their own echo. Turn it on for speakerphone, kiosk, car and
BYO-WebSocket deployments.
