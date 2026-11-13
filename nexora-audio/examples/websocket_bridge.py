"""Run nexora-audio between your clients and your agent platform.

Usage:
    pip install 'nexora-audio[server]'
    python examples/websocket_bridge.py --agent ws://localhost:9000/agent --port 8765

Clients connect to ws://<host>:8765 and send binary PCM16 16 kHz mono audio.
The agent receives cleaned audio plus JSON turn events. See
nexora_audio/integrations/websocket_bridge.py for the full protocol and hooks.
"""

import argparse
import asyncio
import logging

from nexora_audio import AudioFormat
from nexora_audio.integrations.websocket_bridge import BridgeConfig, serve


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", required=True, help="agent platform WebSocket URL")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--encoding", default="pcm16", choices=["pcm16", "float32", "mulaw", "alaw"])
    ap.add_argument("--rate", type=int, default=16000)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO)
    cfg = BridgeConfig(agent_url=args.agent, input_format=AudioFormat(args.encoding, args.rate))
    asyncio.run(serve(cfg, args.host, args.port))


if __name__ == "__main__":
    main()
