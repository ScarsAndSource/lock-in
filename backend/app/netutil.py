"""
Who is really calling.

X-Forwarded-For is a list that every proxy APPENDS to, and the client can put anything it likes at the front:
    X-Forwarded-For: <whatever the client wrote>, <added by the proxy that saw the client>, <added by the next proxy>
Taking the FIRST entry (what the code did before) lets anyone pick their own "IP" and so dodge a per-IP limit or
burn someone else's. The only trustworthy entry is the one added by a proxy YOU run, so we count `hops` entries in
from the RIGHT (trusted_proxy_hops: Render's load balancer = 1, Cloudflare in front of Render = 2).

Anything missing, short or not an IP falls back to the socket peer, so a direct call (local dev, tests) still works.
"""
from __future__ import annotations

import ipaddress

from fastapi import Request


def client_ip(request: Request, hops: int) -> str:
    peer = request.client.host if request.client else "unknown"
    if hops <= 0:
        return peer[:64]
    parts = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
    if len(parts) >= hops:
        try:
            return str(ipaddress.ip_address(parts[-hops]))
        except ValueError:
            pass
    return peer[:64]
