"""Denoise an audio file.

Usage: python examples/process_audio_file.py noisy.wav clean.wav
"""

import sys

from nexora_audio import FeatureUnavailableError, NexoraAudio


def main(src: str, dst: str) -> None:
    audio = NexoraAudio(noise_cancellation=True)
    try:
        audio.initialize()
    except FeatureUnavailableError as err:
        sys.exit(f"Cannot denoise on this system: {err}")
    try:
        report = audio.process_file(input_path=src, output_path=dst)
    finally:
        audio.close()
    print(
        f"{report.duration_s:.1f} s of {report.sample_rate} Hz audio processed in "
        f"{report.processing_s:.2f} s (real-time factor {report.real_time_factor:.3f}), "
        f"backend: {', '.join(report.backends)}"
    )


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
