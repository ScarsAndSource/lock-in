"""
Two small pure-ASGI middlewares (no BaseHTTPMiddleware: it buffers and re-wraps exceptions).

BodyLimitMiddleware
  The old guard only read the Content-Length header, so a chunked upload (no header) was never limited. This counts the
  bytes as they actually arrive and answers 413 as soon as the running total passes the limit. (A request that DOES
  declare an oversized Content-Length is still refused earlier, with its request id, in main.request_context.) FastAPI
  turns any exception raised while reading a body into its own 400, so once the limit is passed the middleware also
  replaces whatever the app answers with the 413. If the app had already started its own response there is nothing
  left to refuse, so the error propagates as before.

SecurityHeadersMiddleware
  Referrer-Policy, X-Frame-Options, a closed Content-Security-Policy (this is a JSON API: it never needs to load
  anything) and, in production, HSTS. Headers a route already set are left alone. The interactive docs get no CSP
  because Swagger UI needs to load its own script.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable
from uuid import uuid4


class RequestTooLarge(Exception):
    pass


def _request_id(headers) -> bytes:
    for name, value in headers:
        if name.lower() == b"x-request-id":
            return value
    return uuid4().hex.encode()


class BodyLimitMiddleware:
    def __init__(self, app, *, max_bytes: int, upload_max_bytes: int, upload_paths: Iterable[str]):
        self.app = app
        self._max = max_bytes
        self._upload_max = upload_max_bytes
        self._upload_paths = frozenset(upload_paths)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = self._upload_max if scope.get("path") in self._upload_paths else self._max
        total = 0
        exceeded = False        # the body went past the limit
        app_started = False     # the app began its OWN response before that, so there is nothing left to refuse
        refused = False

        async def refuse(request_id: bytes | None = None) -> None:
            nonlocal refused
            if refused:
                return
            refused = True
            body = json.dumps({"detail": "Request body too large."}).encode()
            await send({
                "type": "http.response.start", "status": 413,
                "headers": [
                    (b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
                    (b"x-request-id", request_id or uuid4().hex.encode()),
                ],
            })
            await send({"type": "http.response.body", "body": body})

        async def counted_receive():
            nonlocal total, exceeded
            message = await receive()
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > limit:
                    exceeded = True
                    raise RequestTooLarge()
            return message

        async def tracked_send(message):
            # FastAPI turns ANY exception raised while it reads the body into its own 400, so we can't rely on our
            # exception reaching us. Once the limit has been passed, whatever the app answers is replaced by the 413.
            nonlocal app_started
            if exceeded and not app_started:
                await refuse(_request_id(message.get("headers", [])) if message["type"] == "http.response.start" else None)
                return
            if message["type"] == "http.response.start":
                app_started = True
            await send(message)

        try:
            await self.app(scope, counted_receive, tracked_send)
        except (asyncio.CancelledError, KeyboardInterrupt, SystemExit):
            raise
        except BaseException:  # noqa: BLE001 -- ours, or the app's reaction to it; unrelated errors re-raise below
            if exceeded and not app_started:
                await refuse()
                return
            raise


_DOC_PATHS = frozenset({"/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"})
_HSTS = b"max-age=31536000; includeSubDomains"
_CSP = b"default-src 'none'; frame-ancestors 'none'; base-uri 'none'"


class SecurityHeadersMiddleware:
    def __init__(self, app, *, hsts: bool = False):
        self.app = app
        self._hsts = hsts

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        docs = scope.get("path") in _DOC_PATHS

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                present = {name.lower() for name, _ in headers}
                wanted = [(b"referrer-policy", b"no-referrer"), (b"x-frame-options", b"DENY")]
                if not docs:
                    wanted.append((b"content-security-policy", _CSP))
                if self._hsts:
                    wanted.append((b"strict-transport-security", _HSTS))
                headers.extend((n, v) for n, v in wanted if n not in present)
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)
