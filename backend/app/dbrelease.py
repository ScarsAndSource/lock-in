"""
Hand the request's database connection back to the pool while a model call is in flight.

The problem: get_db keeps one transaction (one pooled connection) open for the whole request. On a chat turn that
means the connection sits idle for the seconds Groq takes to answer, so a slow provider pins connections and, with the
pool exhausted, even the plain tracker screens answer 503. The model-call slot (limits/slots.py) already bounds how
many calls run at once; this makes each of them stop holding a connection.

How: get_db installs a hook for the requests that opt in (see db._RELEASE_PATHS). ai_slot() awaits release() BEFORE it
waits for a slot, so neither the wait nor the provider call pins a connection. The hook ends the session's current
transaction (commit) and the session quietly checks a connection out again at its next query, re-applying the RLS
context (db.get_db listens for each new transaction).

Safety rules, all enforced in the hook, not here:
  * a request that has WRITTEN (data_version.is_dirty(): the agent applied something) never releases: its writes and the
    stored reply stay one atomic transaction
  * nothing to release when no transaction is open, or inside a SAVEPOINT
  * only the routes that read before a model call and write after it opt in; every other route is unchanged
release() never raises: a hook failure must not turn a model call into an error.
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from contextvars import ContextVar

logger = logging.getLogger("lockin.dbrelease")

Hook = Callable[[], Awaitable[None]]

_hook: ContextVar[Hook | None] = ContextVar("lockin_db_release", default=None)


def install(hook: Hook) -> None:
    _hook.set(hook)


def clear() -> None:
    _hook.set(None)


async def release() -> None:
    hook = _hook.get()
    if hook is None:
        return
    try:
        await hook()
    except Exception:  # noqa: BLE001 -- the model call goes ahead; the session sorts itself out at its next query
        logger.warning("could not hand the database connection back before a model call", exc_info=True)
