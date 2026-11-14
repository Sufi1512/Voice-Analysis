"""``nexora-audio`` command.

    nexora-audio devices                 list sound devices
    nexora-audio live                    hear your own voice with noise removed
    nexora-audio live --seconds 30 --input 2 --output 4 --rate 48000
    nexora-audio process in.wav out.wav  clean a file

``devices`` and ``live`` need ``pip install nexora-audio[devices]`` (and on Linux the system
PortAudio library, ``libportaudio2``).
"""

from __future__ import annotations

import argparse
import json
import sys
import time


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="nexora-audio")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("devices", help="list sound devices")
    live = sub.add_parser("live", help="microphone -> noise removal -> speaker")
    live.add_argument("--seconds", type=float, default=0, help="stop after this long (0: Ctrl-C)")
    live.add_argument("--input", type=int, default=None, help="input device index")
    live.add_argument("--output", type=int, default=None, help="output device index")
    live.add_argument("--rate", type=int, default=16000)
    live.add_argument("--events", action="store_true", help="print turn events")
    proc = sub.add_parser("process", help="clean a WAV file")
    proc.add_argument("input")
    proc.add_argument("output")
    args = ap.parse_args(argv)

    if args.cmd == "devices":
        from nexora_audio.devices import list_devices

        for d in list_devices():
            print(f"{d['index']:3d}  in {d['inputs']}  out {d['outputs']}  {d['name']}")
        return 0
    if args.cmd == "process":
        from nexora_audio import NexoraAudio

        with NexoraAudio() as nx:
            nx.process_file(args.input, args.output)
        return 0

    from nexora_audio.devices import LiveSession

    def show(ev: object) -> None:
        if args.events:
            print(json.dumps(ev.to_dict()), flush=True)  # type: ignore[attr-defined]

    device = None if args.input is None and args.output is None else (args.input, args.output)
    print("listening (Ctrl-C to stop)...", file=sys.stderr)
    with LiveSession(sample_rate=args.rate, device=device, on_event=show) as s:
        try:
            t0 = time.monotonic()
            while not args.seconds or time.monotonic() - t0 < args.seconds:
                time.sleep(0.2)
        except KeyboardInterrupt:
            pass
    print(json.dumps(s.stats.__dict__), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
