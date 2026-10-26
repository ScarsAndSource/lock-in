"""
LLM usage per day, for the operator (you), across all users. Run it by hand or as a daily Cron Job:

    python -m app.jobs.llm_usage_report                 (last 7 days, text table)
    python -m app.jobs.llm_usage_report --days 30
    python -m app.jobs.llm_usage_report --json

Reads the existing llm_usage table (migration 009): one row per user / UTC day / feature, written by BudgetedLLM.
It shows total calls and tokens per day, split by feature, how many users made calls, the busiest user's count, and how
many users hit LLM_DAILY_CALL_CAP. It prints counts only -- never user ids, never text.

RLS: this sees ALL users, so it runs on a plain owner session, like the other jobs. It must never be imported by, or
exposed through, the HTTP app.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import case, func, select

from app.config import get_settings
from app.db import AsyncSessionLocal
from app.models import LlmUsageORM


def build_report(feature_rows, user_rows, cap: int) -> list[dict]:
    """feature_rows: (day, feature, calls, tokens). user_rows: (day, users, max_user_calls, users_at_cap). Newest day first."""
    days: dict[date, dict] = {}

    def _day(d: date) -> dict:
        return days.setdefault(d, {
            "date": d.isoformat(), "calls": 0, "tokens": 0, "users": 0, "max_user_calls": 0, "users_at_cap": 0,
            "by_feature": {},
        })

    for d, feature, calls, tokens in feature_rows:
        row = _day(d)
        row["calls"] += int(calls or 0)
        row["tokens"] += int(tokens or 0)
        row["by_feature"][feature] = {"calls": int(calls or 0), "tokens": int(tokens or 0)}
    for d, users, max_calls, at_cap in user_rows:
        row = _day(d)
        row["users"], row["max_user_calls"], row["users_at_cap"] = int(users or 0), int(max_calls or 0), int(at_cap or 0)
    return [days[d] for d in sorted(days, reverse=True)]


def render_text(report: list[dict], cap: int) -> str:
    if not report:
        return "No LLM usage recorded in this window."
    features = sorted({f for r in report for f in r["by_feature"]})
    head = ["date", "users", "calls", "tokens", "max/user", f"at cap({cap})", *features]
    lines = [head]
    for r in report:
        lines.append([
            r["date"], r["users"], r["calls"], r["tokens"], r["max_user_calls"], r["users_at_cap"],
            *[r["by_feature"].get(f, {}).get("calls", 0) for f in features],
        ])
    widths = [max(len(str(row[i])) for row in lines) for i in range(len(head))]
    out = ["  ".join(str(c).rjust(w) for c, w in zip(row, widths)) for row in lines]
    out.insert(1, "  ".join("-" * w for w in widths))
    out.append("(feature columns are call counts; tokens are only recorded for completions that report usage)")
    return "\n".join(out)


async def fetch_report(days: int, cap: int, today: date | None = None) -> list[dict]:
    today = today or datetime.now(timezone.utc).date()  # the daily cap resets at 00:00 UTC, so days are UTC days
    since = today - timedelta(days=days - 1)
    async with AsyncSessionLocal() as session:
        feature_rows = (await session.execute(
            select(
                LlmUsageORM.usage_date, LlmUsageORM.feature,
                func.sum(LlmUsageORM.calls), func.sum(LlmUsageORM.tokens),
            )
            .where(LlmUsageORM.usage_date >= since)
            .group_by(LlmUsageORM.usage_date, LlmUsageORM.feature)
        )).all()
        per_user = (
            select(LlmUsageORM.usage_date.label("d"), LlmUsageORM.user_id, func.sum(LlmUsageORM.calls).label("c"))
            .where(LlmUsageORM.usage_date >= since)
            .group_by(LlmUsageORM.usage_date, LlmUsageORM.user_id)
            .subquery()
        )
        user_rows = (await session.execute(
            select(
                per_user.c.d, func.count(), func.max(per_user.c.c),
                func.sum(case((per_user.c.c >= cap, 1), else_=0)),
            ).group_by(per_user.c.d)
        )).all()
    return build_report(feature_rows, user_rows, cap)


async def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="LLM usage per day (all users, counts only).")
    parser.add_argument("--days", type=int, default=7, help="how many UTC days to show, today included (1-90)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)
    days = max(1, min(args.days, 90))
    cap = get_settings().llm_daily_call_cap
    report = await fetch_report(days, cap)
    print(json.dumps({"cap_per_user_per_day": cap, "days": report}, indent=2) if args.json else render_text(report, cap))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
