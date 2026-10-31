"""
Delete AI security events older than AI_EVENT_RETENTION_DAYS (default 30). Run it daily as a Cron Job:

    python -m app.jobs.prune_ai_security_events
    python -m app.jobs.prune_ai_security_events --dry-run     (count only)

To see what needs a human (offenders flagged for review, the global ceiling tripping):

    select created_at, user_id, kind, severity, meta from ai_security_events
    where severity in ('high', 'review') order by created_at desc limit 50;

RLS: this touches every user's rows, so it runs on a plain owner session like the other jobs. It must never be imported
by, or exposed through, the HTTP app.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.config import get_settings
from app.db import AsyncSessionLocal


async def prune(days: int, *, dry_run: bool = False, now: datetime | None = None) -> int:
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=days)
    sql = (
        "select count(*) from public.ai_security_events where created_at < :cutoff" if dry_run
        else "with gone as (delete from public.ai_security_events where created_at < :cutoff returning 1) select count(*) from gone"
    )
    async with AsyncSessionLocal() as session:
        async with session.begin():
            return int((await session.execute(text(sql), {"cutoff": cutoff})).scalar_one())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="prune_ai_security_events")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    days = get_settings().ai_event_retention_days
    count = asyncio.run(prune(days, dry_run=args.dry_run))
    print(f"{'would delete' if args.dry_run else 'deleted'} {count} event(s) older than {days} days")
    return 0


if __name__ == "__main__":
    sys.exit(main())
