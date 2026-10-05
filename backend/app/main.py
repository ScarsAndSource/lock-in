from __future__ import annotations

import logging
import re
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.db import engine, ping_database
from app.exceptions import ConflictError, DataIntegrityError, NotFoundError, RateLimitedError, ValidationError
from app.routers import checkins, habits, missions, profile, screen_time, sleep, stats
from app.schema_check import check_schema

settings = get_settings()
logger = logging.getLogger("lockin")
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9\-]{8,64}$")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO)
    await check_schema(engine, settings.schema_check_mode)
    yield


app = FastAPI(title="Lock'in API", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    incoming = request.headers.get("x-request-id", "")
    request_id = incoming if _REQUEST_ID_RE.match(incoming) else uuid4().hex
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers.setdefault("Cache-Control", "no-store")  # personal data: never cache
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    return response


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


@app.exception_handler(DataIntegrityError)
async def integrity_handler(request: Request, exc: DataIntegrityError) -> JSONResponse:
    logger.error("DATA INTEGRITY: %s request_id=%s", exc, getattr(request.state, "request_id", "?"))
    return JSONResponse(status_code=500, content={"detail": "Stored data failed an integrity check."})


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    logger.exception("Unhandled error request_id=%s path=%s", request_id, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal error.", "request_id": request_id})


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


for module in (habits, checkins, sleep, screen_time, stats, missions, profile):
    app.include_router(module.router)
