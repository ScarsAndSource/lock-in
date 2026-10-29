"""
Operator switch for the AI, no deploy needed. Needs REDIS_URL. Run it by hand:

    python -m app.jobs.ai_switch status [USER_UUID]
    python -m app.jobs.ai_switch pause [--minutes N]        AI off for EVERYONE (omit --minutes = until resume)
    python -m app.jobs.ai_switch resume
    python -m app.jobs.ai_switch ban USER_UUID [--minutes N]    AI off for one user (default 60)
    python -m app.jobs.ai_switch unban USER_UUID
    python -m app.jobs.ai_switch breaker-reset              close the provider breaker now

"Off" means every AI feature takes its deterministic fallback: chat answers with the plain digest, task capture keeps
the person's words, voice/photo parsing says the assistant is unavailable. Habits, tasks, undo, manual logging and the
crisis support path are untouched.

Redis is volatile: a pause or ban is lost if Redis restarts. It prints flags and TTLs only, never text.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from uuid import UUID

from app.limits import aigate
from app.redis_client import close_redis


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ai_switch", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    st = sub.add_parser("status")
    st.add_argument("user", nargs="?", type=UUID)

    pa = sub.add_parser("pause")
    pa.add_argument("--minutes", type=int, default=None)

    sub.add_parser("resume")

    ban = sub.add_parser("ban")
    ban.add_argument("user", type=UUID)
    ban.add_argument("--minutes", type=int, default=60)

    un = sub.add_parser("unban")
    un.add_argument("user", type=UUID)

    sub.add_parser("breaker-reset")
    return p


async def _run(args: argparse.Namespace) -> None:
    if args.cmd == "status":
        s = await aigate.status(args.user)
        print(f"global pause : {'ON' if s['paused_ttl'] is not None else 'off'}"
              + (f" (ttl {s['paused_ttl']}s)" if s["paused_ttl"] not in (None, -1) else ""))
        print(f"breaker      : {'OPEN' if s['breaker_open_ttl'] is not None else 'closed'}"
              + (f" (ttl {s['breaker_open_ttl']}s)" if s["breaker_open_ttl"] not in (None, -1) else ""))
        if args.user is not None:
            print(f"user ban     : {'ON' if s['user_ban_ttl'] is not None else 'off'}"
                  + (f" (ttl {s['user_ban_ttl']}s)" if s["user_ban_ttl"] not in (None, -1) else ""))
    elif args.cmd == "pause":
        await aigate.pause_all(args.minutes * 60 if args.minutes else None)
        print("AI paused for everyone" + (f" for {args.minutes} min." if args.minutes else " until you run resume."))
    elif args.cmd == "resume":
        await aigate.resume_all()
        print("AI resumed.")
    elif args.cmd == "ban":
        await aigate.ban_user(args.user, max(1, args.minutes) * 60)
        print(f"AI off for that user for {max(1, args.minutes)} min.")
    elif args.cmd == "unban":
        await aigate.unban_user(args.user)
        print("AI back on for that user.")
    elif args.cmd == "breaker-reset":
        await aigate.reset_breaker()
        print("Breaker closed.")


async def _main() -> int:
    args = _parser().parse_args()
    try:
        await _run(args)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        await close_redis()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
