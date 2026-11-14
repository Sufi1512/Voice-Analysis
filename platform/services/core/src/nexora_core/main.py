"""Entry point: ``nexora-core`` runs the API with uvicorn."""

import os

import uvicorn

from nexora_core.app import create_app


def run() -> None:
    host = os.environ.get("NEXORA_HOST", "0.0.0.0")  # noqa: S104 - containers listen on all interfaces
    uvicorn.run(create_app(), host=host, port=int(os.environ.get("NEXORA_PORT", "8080")))
