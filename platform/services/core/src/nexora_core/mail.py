"""Outgoing email over plain SMTP (aiosmtplib). No provider API: any in-Kingdom relay works."""

from email.message import EmailMessage
from email.utils import make_msgid

import aiosmtplib

from nexora_core.logging import get_logger
from nexora_core.settings import Settings

log = get_logger(__name__)
SMTP_TIMEOUT_S = 10


class MailError(Exception):
    """The message could not be handed to the SMTP server."""


def header_safe(value: str) -> str:
    """No CR or LF in headers: user-controlled text (an organization name) can't add headers."""
    return " ".join(value.replace("\r", " ").replace("\n", " ").split())


class Mailer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def send(self, *, to: str, subject: str, body: str) -> None:
        s = self.settings
        msg = EmailMessage()
        msg["From"] = s.smtp_from
        msg["To"] = header_safe(to)
        msg["Subject"] = header_safe(subject)
        msg["Message-ID"] = make_msgid(domain="nexora")
        msg.set_content(body)
        try:
            await aiosmtplib.send(
                msg,
                hostname=s.smtp_host,
                port=s.smtp_port,
                username=s.smtp_username or None,
                password=s.smtp_password.get_secret_value() or None,
                use_tls=s.smtp_security == "tls",
                start_tls=s.smtp_security == "starttls",
                timeout=SMTP_TIMEOUT_S,
            )
        except (aiosmtplib.SMTPException, OSError) as exc:
            log.warning("email not sent", error=type(exc).__name__)
            raise MailError(type(exc).__name__) from exc
