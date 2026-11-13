"""Which agent URLs the relay may connect to (SSRF protection)."""

from __future__ import annotations

import ipaddress
import socket
from fnmatch import fnmatch
from urllib.parse import urlsplit


class RelayTargetError(ValueError):
    pass


def check_relay_target(url: str, allowlist: list[str], deployment_mode: str) -> str:
    """Validate a relay target URL. Returns the host. Raises RelayTargetError.

    Rules: ``ws``/``wss`` only; the host must match the organization's allowlist
    (exact host or ``*.domain``). In SaaS mode the host must not resolve to a
    private, loopback, link-local or otherwise internal address.
    """
    parts = urlsplit(url)
    if parts.scheme not in ("ws", "wss"):
        raise RelayTargetError("relay target must be a ws:// or wss:// URL")
    if deployment_mode == "saas" and parts.scheme != "wss":
        raise RelayTargetError("relay target must use wss:// (TLS)")
    host = (parts.hostname or "").lower()
    if not host:
        raise RelayTargetError("relay target has no host")
    if parts.username or parts.password:
        raise RelayTargetError("credentials in the relay URL are not allowed")
    if not any(fnmatch(host, pattern.lower()) for pattern in allowlist):
        raise RelayTargetError(f"host {host!r} is not on this organization's relay allowlist")
    if deployment_mode == "saas":
        _reject_internal(host, parts.port or 443)
    return host


def _reject_internal(host: str, port: int) -> None:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise RelayTargetError(f"cannot resolve {host!r}") from exc
    for info in infos:
        addr = ipaddress.ip_address(info[4][0])
        if (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
            or addr.is_multicast
            or addr.is_unspecified
        ):
            raise RelayTargetError(f"{host!r} resolves to a non-public address")
