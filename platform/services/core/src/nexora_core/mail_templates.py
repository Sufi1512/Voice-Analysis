"""Email texts (English for now; every string here moves to translation files with Arabic)."""

from datetime import datetime

from nexora_core.authz.catalogue import ROLE_NAMES


def invitation(
    *, organization: str, role: str, inviter: str, link: str, expires_at: datetime
) -> tuple[str, str]:
    subject = f"You're invited to {organization} on NEXORA"
    body = (
        f"{inviter} invited you to join {organization} on NEXORA as {ROLE_NAMES[role]}.\n\n"
        f"Accept the invitation: {link}\n\n"
        f"The link works once and expires on {expires_at:%Y-%m-%d %H:%M} UTC.\n"
        "If you weren't expecting this, you can ignore this email.\n"
    )
    return subject, body
