"""Which web addresses may be fetched: public http(s) only, never a private or link-local network.

Accepted residual risk (local, login-protected, single-user demo): the host is resolved here and
resolved again by httpx when connecting, so a DNS-rebinding host could pass this check and then
answer with a private address. Closing it needs a transport pinned to the checked IP.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


def public_url(url: str) -> str | None:
    """None when url is an http(s) address on the public internet; else why it is refused."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return "only http:// or https:// links can be read"
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(parsed.hostname, None)}
    except OSError as exc:
        return f"the address could not be looked up ({exc})"
    for address in addresses:
        if not ipaddress.ip_address(address.split("%")[0]).is_global:
            return "the link points inside a private network, so it is not read"
    return None
