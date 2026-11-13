"""Process a live-style stream of 10 ms chunks (simulated from a file).

Usage: python examples/streaming_chunks.py input.wav
Each processed chunk is what you would send to an STT engine, a WebRTC track
or a voice agent.
"""

import sys

import numpy as np
import soundfile as sf

from nexora_audio import NexoraAudio


def main(path: str) -> None:
    data, rate = sf.read(path, dtype="int16", always_2d=True)
    data = data[:, :1]  # mono
    with NexoraAudio(sample_rate=rate, frame_ms=10) as audio:
        step = audio.config.frame_samples
        out = [audio.process_chunk(data[i : i + step]) for i in range(0, len(data), step)]
        out.append(audio.flush(like=data))
        print(
            f"latency {audio.latency.algorithmic_ms:.1f} ms, "
            f"per-chunk p50 {audio.timing.p50_ms:.2f} ms, p99 {audio.timing.p99_ms:.2f} ms"
        )
    sf.write("streamed_output.wav", np.concatenate(out), rate)
    print("wrote streamed_output.wav")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
