"""An in-process SMTP server for tests (real SMTP protocol, messages kept in memory)."""

import email
import email.policy
import socket
from typing import TYPE_CHECKING

from aiosmtpd.controller import Controller

if TYPE_CHECKING:
    from email.message import EmailMessage


class Inbox:
    def __init__(self) -> None:
        self.messages: list[EmailMessage] = []

    async def handle_DATA(self, _server, _session, envelope):  # noqa: N802 - aiosmtpd hook name
        msg = email.message_from_bytes(envelope.content, policy=email.policy.default)
        msg["X-Envelope-To"] = ", ".join(envelope.rcpt_tos)
        self.messages.append(msg)  # ty: ignore[invalid-argument-type]
        return "250 OK"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_smtp() -> tuple[Controller, Inbox]:
    inbox = Inbox()
    controller = Controller(inbox, hostname="127.0.0.1", port=free_port())
    controller.start()
    return controller, inbox


class FakeMailer:
    """Records messages instead of sending them, for tests that aren't about delivery."""

    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []

    async def send(self, *, to: str, subject: str, body: str) -> None:
        self.sent.append({"to": to, "subject": subject, "body": body})
