"""``nexora-server`` command: run the API server.

Examples:
    NEXORA_SECRET_KEY=... NEXORA_ADMIN_API_KEY=... nexora-server --port 8080
    NEXORA_DATABASE_URL=postgresql+psycopg://user:pass@db/nexora nexora-server
"""

from __future__ import annotations

import argparse


def main() -> None:
    import uvicorn

    from nexora_server.app import create_app

    ap = argparse.ArgumentParser(prog="nexora-server")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--no-prewarm", action="store_true", help="skip loading models at startup")
    args = ap.parse_args()
    app = create_app(prewarm=not args.no_prewarm)
    # one process per instance: audio work runs in the app's own thread pool;
    # scale out with more instances behind a load balancer
    uvicorn.run(app, host=args.host, port=args.port, ws_max_size=16 * 1024 * 1024, log_config=None)


if __name__ == "__main__":
    main()
