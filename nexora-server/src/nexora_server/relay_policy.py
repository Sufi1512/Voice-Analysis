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


def _reject_internal(host: str, port: int) -> list[str]:
    """Resolve once; refuse if any address is internal. Returns the vetted addresses."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise RelayTargetError(f"cannot resolve {host!r}") from exc
    vetted = []
    for info in infos:
        addr: ipaddress.IPv4Address | ipaddress.IPv6Address = ipaddress.ip_address(info[4][0])
        if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
            addr = addr.ipv4_mapped  # ::ffff:10.0.0.1 is 10.0.0.1
        if (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
            or addr.is_multicast
            or addr.is_unspecified
        ):
            raise RelayTargetError(f"{host!r} resolves to a non-public address")
        vetted.append(str(addr))
    return vetted


def open_vetted_socket(
    url: str, deployment_mode: str, timeout: float = 10.0
) -> socket.socket | None:
    """SaaS mode: connect a TCP socket to an address that was checked in the same step, so
    DNS cannot change between the check and the connection (DNS rebinding). Self-hosted
    mode: None (connect normally)."""
    if deployment_mode != "saas":
        return None
    parts = urlsplit(url)
    host, port = (
        (parts.hostname or "").lower(),
        parts.port or (443 if parts.scheme == "wss" else 80),
    )
    last: OSError | None = None
    for addr in _reject_internal(host, port):
        try:
            return socket.create_connection((addr, port), timeout=timeout)
        except OSError as exc:
            last = exc
    raise RelayTargetError(f"cannot connect to {host!r}: {last}")
