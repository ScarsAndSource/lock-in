from __future__ import annotations

import logging
import re
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import get_settings
from app.db import engine, ping_database
from app.exceptions import (
    ConflictError, DailyLimitError, DataIntegrityError, NotFoundError, RateLimitedError,
    ServiceUnavailableError, ValidationError,
)
from app.routers import (
    chat, chat_threads, checkins, goals, habits, insights, intentions, missions, mood, notifications,
    pause_shortcuts, pauses, profile, retros, screen_time, sleep, stats,
    study, support, tasks, urges,
)
from app.schema_check import check_schema

settings = get_settings()
logger = logging.getLogger("lockin")
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9\-]{8,64}$")
_MAX_BODY_BYTES = 256 * 1024
# The only routes that take a file. The services re-check the real size while reading, so this is just the front gate.
_UPLOAD_BODY_BYTES = 5 * 1024 * 1024
_UPLOAD_PATHS = frozenset({"/checkins/voice", "/screen-time/parse-screenshot"})


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO)
    await check_schema(engine, settings.schema_check_mode)
    yield


app = FastAPI(title="Lock'in API", version="0.2.0", lifespan=lifespan)

def _detail(code: int, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=code, content={"detail": str(exc)})


@app.exception_handler(NotFoundError)
async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    return _detail(status.HTTP_404_NOT_FOUND, exc)


@app.exception_handler(ValidationError)
async def validation_error_handler(request: Request, exc: ValidationError) -> JSONResponse:
    return _detail(status.HTTP_422_UNPROCESSABLE_ENTITY, exc)


@app.exception_handler(ConflictError)
async def conflict_handler(request: Request, exc: ConflictError) -> JSONResponse:
    return _detail(status.HTTP_409_CONFLICT, exc)


@app.exception_handler(RateLimitedError)
async def rate_limited_handler(request: Request, exc: RateLimitedError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"detail": "Too many requests. Slow down."},
        headers={"Retry-After": str(exc.retry_after)},
    )


@app.exception_handler(DailyLimitError)
async def daily_limit_handler(request: Request, exc: DailyLimitError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"detail": "You've used today's AI allowance. It resets at 00:00 UTC."},
        headers={"Retry-After": str(exc.retry_after)},
    )


@app.exception_handler(ServiceUnavailableError)
async def unavailable_handler(request: Request, exc: ServiceUnavailableError) -> JSONResponse:
    return _detail(status.HTTP_503_SERVICE_UNAVAILABLE, exc)


@app.exception_handler(DataIntegrityError)
async def integrity_handler(request: Request, exc: DataIntegrityError) -> JSONResponse:
    logger.error("DATA INTEGRITY: %s request_id=%s", exc, getattr(request.state, "request_id", "?"))
    return JSONResponse(status_code=500, content={"detail": "Stored data failed an integrity check."})


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    logger.exception("Unhandled error request_id=%s path=%s", request_id, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal error.", "request_id": request_id})


class BodyTooLargeError(Exception):
    pass


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers_dict = dict(scope.get("headers", []))
        incoming = headers_dict.get(b"x-request-id", b"").decode("latin1")
        request_id = incoming if _REQUEST_ID_RE.match(incoming) else uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id

        path = scope.get("path", "")
        limit = _UPLOAD_BODY_BYTES if path in _UPLOAD_PATHS else _MAX_BODY_BYTES
        length = headers_dict.get(b"content-length", b"").decode("latin1")
        if length.isdigit() and int(length) > limit:
            response = JSONResponse(
                status_code=413, content={"detail": "Request body too large."}, headers={"X-Request-ID": request_id},
            )
            response.headers.setdefault("Cache-Control", "no-store")
            response.headers.setdefault("X-Content-Type-Options", "nosniff")
            await response(scope, receive, send)
            return

        received_bytes = 0
        response_started = False

        async def custom_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                m_headers = MutableHeaders(scope=message)
                m_headers["X-Request-ID"] = request_id
                m_headers.setdefault("Cache-Control", "no-store")
                m_headers.setdefault("X-Content-Type-Options", "nosniff")
            await send(message)

        async def custom_receive() -> Message:
            nonlocal received_bytes
            message = await receive()
            if message["type"] == "http.request":
                body = message.get("body", b"")
                received_bytes += len(body)
                if received_bytes > limit:
                    raise BodyTooLargeError()
            return message

        try:
            await self.app(scope, custom_receive, custom_send)
        except BodyTooLargeError:
            if not response_started:
                response = JSONResponse(
                    status_code=413, content={"detail": "Request body too large."}, headers={"X-Request-ID": request_id},
                )
                response.headers.setdefault("Cache-Control", "no-store")
                response.headers.setdefault("X-Content-Type-Options", "nosniff")
                await response(scope, receive, send)
            else:
                raise
        except Exception as exc:
            if not response_started:
                request = Request(scope)
                response = await unhandled_handler(request, exc)
                response.headers["X-Request-ID"] = request_id
                response.headers.setdefault("Cache-Control", "no-store")
                response.headers.setdefault("X-Content-Type-Options", "nosniff")
                await response(scope, receive, send)
            else:
                raise


app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["meta"])
async def health() -> dict:
    return {"status": "ok"}


@app.get("/ready", tags=["meta"])
async def ready():
    try:
        await ping_database()
    except Exception:  # noqa: BLE001 -- logged, reported as 503
        logger.exception("Readiness check failed")
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return {"status": "ready"}


for module in (
    habits, checkins, sleep, screen_time, stats, missions, profile, retros, insights,
    study, urges, goals, intentions, chat, chat_threads, support, pauses, pause_shortcuts,
    tasks, notifications, mood,
):
    app.include_router(module.router)

