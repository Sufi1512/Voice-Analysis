"""``nexora-server`` command: run the API server, or ``nexora-server migrate``.

Examples:
    NEXORA_SECRET_KEY=... NEXORA_ADMIN_API_KEY=... nexora-server --port 8080
    NEXORA_DATABASE_URL=postgresql+psycopg://user:pass@db/nexora nexora-server
    NEXORA_DATABASE_URL=... nexora-server migrate

On SIGTERM the server drains: it stops taking new sessions, lets open ones finish (up to
``NEXORA_DRAIN_TIMEOUT_S``), then exits. A second SIGTERM exits at once.
"""

from __future__ import annotations

import argparse
import logging
import threading
import time
from types import FrameType
from typing import Any

log = logging.getLogger("nexora.main")


def _server_class() -> Any:
    import uvicorn

    class DrainingServer(uvicorn.Server):
        """Uvicorn closes open WebSockets as soon as it shuts down; drain first."""

        def __init__(self, config: uvicorn.Config, app: Any, drain_timeout_s: float) -> None:
            super().__init__(config)
            self.nexora_app = app
            self.drain_timeout_s = drain_timeout_s
            self._draining = False

        def handle_exit(self, sig: int, frame: FrameType | None) -> None:
            if self._draining or not getattr(self.nexora_app.state, "ready", False):
                super().handle_exit(sig, frame)  # second signal, or not started: exit now
                return
            self._draining = True
            self.nexora_app.state.start_draining()
            threading.Thread(
                target=self._exit_when_idle, args=(sig, frame), daemon=True, name="drain"
            ).start()

        def _exit_when_idle(self, sig: int, frame: FrameType | None) -> None:
            wait_until_idle(self.nexora_app.state.manager, self.drain_timeout_s)
            super().handle_exit(sig, frame)

    return DrainingServer


def wait_until_idle(manager: Any, timeout_s: float, poll_s: float = 0.5) -> bool:
    """Block until the manager has no open sessions (True) or the timeout passes (False)."""
    deadline = time.monotonic() + timeout_s
    while manager.active > 0:
        if time.monotonic() >= deadline:
            log.warning("drain timeout: closing %d open sessions", manager.active)
            return False
        time.sleep(poll_s)
    return True


def main() -> None:
    import uvicorn

    ap = argparse.ArgumentParser(prog="nexora-server")
    ap.add_argument("command", nargs="?", choices=["serve", "migrate"], default="serve")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--no-prewarm", action="store_true", help="skip loading models at startup")
    args = ap.parse_args()

    from nexora_server.settings import Settings

    settings = Settings.from_env()
    if args.command == "migrate":
        from nexora_server.migrate import upgrade

        logging.basicConfig(level=logging.INFO)
        upgrade(settings.database_url)
        return

    from nexora_server.app import create_app

    app = create_app(settings, prewarm=not args.no_prewarm)
    # one process per instance: audio work runs in the app's own thread pool;
    # scale out with more instances behind a load balancer
    config = uvicorn.Config(
        app, host=args.host, port=args.port, ws_max_size=16 * 1024 * 1024, log_config=None
    )
    _server_class()(config, app, settings.drain_timeout_s).run()


if __name__ == "__main__":
    main()
