from __future__ import annotations

import asyncio
import logging
import re
from contextlib import asynccontextmanager
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from app import audit
from app.audit_sql import write_event
from app.config import get_settings
from app.db import engine, ping_database
from app.exceptions import (
    ConflictError, DailyLimitError, DataIntegrityError, NotFoundError, RateLimitedError,
    ServiceUnavailableError, ValidationError,
)
from app.routers import calendar as calendar_router
from app.routers import (
    actions, chat_actions, companion, experiments, inference, ingest, chat_threads, checkins, goals, habits, insights, intentions, missions, mood, notifications,
    pause_shortcuts, pauses, profile, retros, screen_time, sleep, stats,
    study, support, tasks, urges, growth, crew, journey,
)
from app.middleware import BodyLimitMiddleware, SecurityHeadersMiddleware
from app.observability import init_sentry, tag_request
from app.redis_client import close_redis, safe
from app.schema_check import check_schema

settings = get_settings()
init_sentry(settings)  # before the app object exists, as Sentry recommends
logger = logging.getLogger("lockin")
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9\-]{8,64}$")
_MAX_BODY_BYTES = 256 * 1024
_READY_TIMEOUT_SECONDS = 5
# The only routes that take a file. The services re-check the real size while reading, so this is just the front gate.
_UPLOAD_BODY_BYTES = 5 * 1024 * 1024
_UPLOAD_PATHS = frozenset({
    "/checkins/voice", "/screen-time/parse-screenshot", "/calendar/parse-image", "/growth/future",
})
# /ingest/u/<token>/<kind> carries a credential in the path: it must never reach a log line.
_INGEST_TOKEN_PATH = re.compile(r"(/ingest/u/)[^/?\s]+")


def redact_path(path: str) -> str:
    return _INGEST_TOKEN_PATH.sub(r"\1***", path)


class _RedactIngestToken(logging.Filter):
    """uvicorn's access log is (client, method, path, http_version, status): scrub the path in place."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str):
            record.args = (*args[:2], redact_path(args[2]), *args[3:])
        return True


logging.getLogger("uvicorn.access").addFilter(_RedactIngestToken())


def describe_redis(url: str) -> str:
    """Host and port only: the URL carries the password."""
    if not url:
        return "not configured: rate limits, locks, caches and card nonces are per-process and reset on restart"
    parts = urlsplit(url)
    return f"configured ({parts.scheme}://{parts.hostname}:{parts.port or ''})"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO)
    logger.info("Redis: %s", describe_redis(settings.redis_url))
    audit.set_sink(write_event)                  # security events also go to ai_security_events (migration 028)
    await check_schema(engine, settings.schema_check_mode)
    try:
        yield
    finally:
        audit.set_sink(None)
        await close_redis()


app = FastAPI(title="Lock'in API", version="0.2.0", lifespan=lifespan)


@app.middleware("http")
async def request_context(request: Request, call_next):
    incoming = request.headers.get("x-request-id", "")
    request_id = incoming if _REQUEST_ID_RE.match(incoming) else uuid4().hex
    request.state.request_id = request_id
    audit.request_id_var.set(request_id)
    tag_request(request_id)
    length = request.headers.get("content-length", "")
    limit = _UPLOAD_BODY_BYTES if request.url.path in _UPLOAD_PATHS else _MAX_BODY_BYTES
    if length.isdigit() and int(length) > limit:
        return JSONResponse(
            status_code=413, content={"detail": "Request body too large."}, headers={"X-Request-ID": request_id},
        )
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers.setdefault("Cache-Control", "no-store")  # personal data: never cache
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    return response


# Stack, outermost first: CORS, security headers, streaming body limit, request_context. CORS stays outermost so early
# responses (413) still carry CORS headers. The body limit catches chunked uploads that declare no Content-Length.
app.add_middleware(
    BodyLimitMiddleware,
    max_bytes=_MAX_BODY_BYTES, upload_max_bytes=_UPLOAD_BODY_BYTES, upload_paths=_UPLOAD_PATHS,
)
app.add_middleware(SecurityHeadersMiddleware, hsts=settings.app_env.strip().lower() in {"production", "prod"})
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    # Exactly what the web app sends (src/api/client.ts, src/api/chat.ts). Add a name here if the client gains a header.
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
    expose_headers=["Retry-After", "X-Request-ID"],   # without this the browser hides them from fetch()
)


def _cors_headers(request: Request) -> dict[str, str]:
    """Starlette's outermost error layer sits outside CORSMiddleware, so a 500 would reach the browser as a CORS error."""
    origin = request.headers.get("origin")
    if origin and origin in settings.cors_allow_origins:
        return {"Access-Control-Allow-Origin": origin, "Access-Control-Allow-Credentials": "true", "Vary": "Origin"}
    return {}


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


@app.exception_handler(PoolTimeoutError)
async def pool_timeout_handler(request: Request, exc: PoolTimeoutError) -> JSONResponse:
    """Every database connection is in use (usually slow model calls). Answer fast instead of queueing forever."""
    logger.warning("DB pool exhausted request_id=%s path=%s", getattr(request.state, "request_id", "?"), redact_path(request.url.path))
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "Busy right now. Try again in a moment."},
        headers={"Retry-After": "2"},
    )


@app.exception_handler(DataIntegrityError)
async def integrity_handler(request: Request, exc: DataIntegrityError) -> JSONResponse:
    logger.error("DATA INTEGRITY: %s request_id=%s", exc, getattr(request.state, "request_id", "?"))
    return JSONResponse(status_code=500, content={"detail": "Stored data failed an integrity check."})


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    logger.exception("Unhandled error request_id=%s path=%s", request_id, redact_path(request.url.path))
    return JSONResponse(
        status_code=500, content={"detail": "Internal error.", "request_id": request_id}, headers=_cors_headers(request),
    )


# GET and HEAD: several uptime monitors probe with HEAD, which a GET-only route answers with 405 (a false "down").
@app.api_route("/health", methods=["GET", "HEAD"], tags=["meta"])
async def health() -> dict:
    return {"status": "ok"}


@app.api_route("/ready", methods=["GET", "HEAD"], tags=["meta"])
async def ready():
    try:
        await asyncio.wait_for(ping_database(), timeout=_READY_TIMEOUT_SECONDS)  # a hung DB must read as "down", not hang the monitor
    except Exception:  # noqa: BLE001 -- logged, reported as 503
        logger.exception("Readiness check failed")
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    redis_state = "off"
    if settings.redis_url:
        redis_state = "up" if await safe(lambda r: r.ping(), None) else "down"
    return {"status": "ready", "redis": redis_state}


for module in (
    habits, checkins, sleep, screen_time, stats, missions, profile, retros, insights,
    study, urges, goals, intentions, chat_threads, support, pauses, pause_shortcuts,
    tasks, notifications, mood, actions, chat_actions, ingest, companion, experiments, inference, calendar_router,
    growth, crew, journey,
):
    app.include_router(module.router)
