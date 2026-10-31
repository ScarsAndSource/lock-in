"""
Error reporting (Sentry). Off unless SENTRY_DSN is set, so local dev and tests never import or call it.

This app stores journals, urge notes and check-ins, so the SDK is configured to send as little as possible:
  * no request bodies, cookies, headers, query strings or user identity (send_default_pii off + scrubbed again below)
  * no stack-frame local variables (they would carry decrypted text)
  * no breadcrumbs (log lines and SQL would otherwise ride along)
  * the /ingest/u/<token> credential is masked in every URL and transaction name
What stays: exception type, message, the stack trace, route template, status, release, environment and the
request_id tag, which is the same id the API returns in its 500 body and logs -- so a user's "request_id" maps to an event.
"""
from __future__ import annotations

import logging
import os
import re

from app.config import Settings

logger = logging.getLogger("lockin")
_INGEST_TOKEN = re.compile(r"(/ingest/u/)[^/?\s]+")  # same rule as app.main.redact_path (kept here to avoid a circular import)
_enabled = False


def _mask(value: str) -> str:
    return _INGEST_TOKEN.sub(r"\1***", value)


def scrub_event(event: dict, hint: dict | None = None) -> dict | None:
    request = event.get("request")
    if isinstance(request, dict):
        for key in ("data", "cookies", "headers", "env", "query_string"):
            request.pop(key, None)
        if isinstance(request.get("url"), str):
            request["url"] = _mask(request["url"])
    event.pop("user", None)
    event.pop("breadcrumbs", None)
    if isinstance(event.get("transaction"), str):
        event["transaction"] = _mask(event["transaction"])
    return event


def init_sentry(settings: Settings) -> bool:
    """Returns True when reporting is on. Never raises: a broken monitoring setup must not stop the API starting."""
    global _enabled
    if not settings.sentry_dsn:
        return False
    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.app_env,
            release=settings.release or os.environ.get("RENDER_GIT_COMMIT") or None,
            traces_sample_rate=settings.sentry_traces_sample_rate,
            send_default_pii=False,
            include_local_variables=False,
            max_request_body_size="never",
            max_breadcrumbs=0,
            before_send=scrub_event,
            before_send_transaction=scrub_event,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Sentry init failed; continuing without error reporting")
        return False
    _enabled = True
    logger.info("Sentry error reporting enabled")
    return True


def report(message: str, level: str = "error") -> None:
    """A message-only event (no exception) for things an operator should see: the AI ceiling tripping, an abuse review.
    No-op unless Sentry is on. Pass counts and codes, never user text. Never raises."""
    if not _enabled:
        return
    try:
        import sentry_sdk

        sentry_sdk.capture_message(message, level=level)
    except Exception:  # noqa: BLE001
        logger.exception("Sentry report failed")


def tag_request(request_id: str) -> None:
    if not _enabled:
        return
    import sentry_sdk

    sentry_sdk.set_tag("request_id", request_id)
