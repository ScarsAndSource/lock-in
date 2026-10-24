"""Thin wrapper over the crew_* SQL functions (see migrations 024/025). The functions own the rules and the
privacy boundary; this class only binds parameters and decodes the jsonb result. Results are cast to text so
the decoding never depends on the driver's json codec."""
from __future__ import annotations

import json
from datetime import date
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class SqlAlchemySocialRepository:
    def __init__(self, session: AsyncSession):
        self._s = session

    async def _fn(self, call: str, **params) -> dict:
        row = (await self._s.execute(text(f"select ({call})::text"), params)).scalar_one()
        return json.loads(row)

    async def overview(self) -> dict:
        return await self._fn("public.crew_overview()")

    async def set_username(self, username: str) -> dict:
        return await self._fn("public.crew_set_username(cast(:u as text))", u=username)

    async def set_share(self, share: dict[str, bool]) -> dict:
        return await self._fn("public.crew_set_share(cast(cast(:s as text) as jsonb))", s=json.dumps(share))

    async def create(self, name: str) -> dict:
        return await self._fn("public.crew_create(cast(:n as text))", n=name)

    async def invite(self, crew_id: UUID, username: str) -> dict:
        return await self._fn("public.crew_invite(cast(:c as uuid), cast(:u as text))", c=crew_id, u=username)

    async def respond(self, crew_id: UUID, accept: bool) -> dict:
        return await self._fn("public.crew_respond(cast(:c as uuid), cast(:a as boolean))", c=crew_id, a=accept)

    async def make_code(self, crew_id: UUID, revoke: bool) -> dict:
        return await self._fn("public.crew_make_code(cast(:c as uuid), cast(:r as boolean))", c=crew_id, r=revoke)

    async def join(self, code: str) -> dict:
        return await self._fn("public.crew_join_code(cast(:k as text))", k=code)

    async def leave(self, crew_id: UUID) -> dict:
        return await self._fn("public.crew_leave(cast(:c as uuid))", c=crew_id)

    async def set_quiet(self, crew_id: UUID, quiet: bool) -> dict:
        return await self._fn("public.crew_set_quiet(cast(:c as uuid), cast(:q as boolean))", c=crew_id, q=quiet)

    async def block(self, username: str) -> dict:
        return await self._fn("public.crew_block(cast(:u as text))", u=username)

    async def unblock(self, username: str) -> dict:
        return await self._fn("public.crew_unblock(cast(:u as text))", u=username)

    async def card(self, crew_id: UUID, week: date) -> dict:
        return await self._fn("public.crew_card(cast(:c as uuid), cast(:w as date))", c=crew_id, w=week)

    async def send_cheer(self, crew_id: UUID, to: str, kind: str) -> dict:
        return await self._fn(
            "public.crew_send_cheer(cast(:c as uuid), cast(:t as text), cast(:k as text))", c=crew_id, t=to, k=kind,
        )

    async def send_boost(self, crew_id: UUID, to: str | None) -> dict:
        return await self._fn("public.crew_send_boost(cast(:c as uuid), cast(:t as text))", c=crew_id, t=to)

    async def inbox(self) -> dict:
        return await self._fn("public.crew_inbox()")

    async def inbox_seen(self) -> dict:
        return await self._fn("public.crew_inbox_seen()")

    # ---- own snapshot rows (allowed by the owner RLS policies in 025)
    async def snapshot_exists(self, user_id: UUID, week_start: date) -> bool:
        row = await self._s.execute(
            text("select exists (select 1 from public.weekly_snapshots where user_id = :u and week_start = :w)"),
            {"u": user_id, "w": week_start},
        )
        return bool(row.scalar_one())

    async def close_week(
        self, user_id: UUID, week_start: date, *, days_showed: int | None, days_planned: int | None,
        marks: int | None, study_minutes: int | None, proud: str | None, focus: str | None,
        habits: list[str] | None,
    ) -> bool:
        """Write-once: a second close of the same week changes nothing and returns False."""
        res = await self._s.execute(
            text(
                "insert into public.weekly_snapshots "
                "(user_id, week_start, days_showed, days_planned, marks, study_minutes, proud, focus, habits) "
                "values (:u, :w, :ds, :dp, :mk, :sm, :pr, :fo, cast(:hb as text[])) "
                "on conflict (user_id, week_start) do nothing"
            ),
            {
                "u": user_id, "w": week_start, "ds": days_showed, "dp": days_planned, "mk": marks,
                "sm": study_minutes, "pr": proud, "fo": focus, "hb": habits,
            },
        )
        return res.rowcount == 1

    def savepoint(self):
        """`async with repo.savepoint():` -- a failed statement inside rolls back to here, not the whole transaction."""
        return self._s.begin_nested()

    # ---- phase 4/5
    async def goal(self, crew_id: UUID, week: date) -> dict:
        return await self._fn("public.crew_goal(cast(:c as uuid), cast(:w as date))", c=crew_id, w=week)

    async def set_goal(self, crew_id: UUID, week: date, hours: int | None) -> dict:
        return await self._fn(
            "public.crew_set_goal(cast(:c as uuid), cast(:w as date), cast(:h as integer))", c=crew_id, w=week, h=hours,
        )

    async def buddy_propose(self, crew_id: UUID, to: str, threshold: int, message: str, auto: bool) -> dict:
        return await self._fn(
            "public.crew_buddy_propose(cast(:c as uuid), cast(:t as text), cast(:n as integer), "
            "cast(:m as text), cast(:a as boolean))",
            c=crew_id, t=to, n=threshold, m=message, a=auto,
        )

    async def buddy_respond(self, deal_id: UUID, accept: bool, today: date) -> dict:
        return await self._fn(
            "public.crew_buddy_respond(cast(:d as uuid), cast(:a as boolean), cast(:w as date))",
            d=deal_id, a=accept, w=today,
        )

    async def buddy_cancel(self, deal_id: UUID) -> dict:
        return await self._fn("public.crew_buddy_cancel(cast(:d as uuid))", d=deal_id)

    async def buddy_dismiss(self, deal_id: UUID, today: date) -> dict:
        return await self._fn("public.crew_buddy_dismiss(cast(:d as uuid), cast(:w as date))", d=deal_id, w=today)

    async def buddy_send(self, deal_id: UUID, today: date) -> dict:
        return await self._fn("public.crew_buddy_send(cast(:d as uuid), cast(:w as date))", d=deal_id, w=today)

    async def buddy_list(self) -> dict:
        return await self._fn("public.crew_buddy_list()")

    async def duel_propose(self, crew_id: UUID, to: str, week: date) -> dict:
        return await self._fn(
            "public.crew_duel_propose(cast(:c as uuid), cast(:t as text), cast(:w as date))", c=crew_id, t=to, w=week,
        )

    async def duel_respond(self, duel_id: UUID, accept: bool) -> dict:
        return await self._fn("public.crew_duel_respond(cast(:d as uuid), cast(:a as boolean))", d=duel_id, a=accept)

    async def duel_cancel(self, duel_id: UUID) -> dict:
        return await self._fn("public.crew_duel_cancel(cast(:d as uuid))", d=duel_id)

    async def duel_score(self, duel_id: UUID, ratio_milli: int, baseline_milli: int) -> dict:
        return await self._fn(
            "public.crew_duel_score(cast(:d as uuid), cast(:r as integer), cast(:b as integer))",
            d=duel_id, r=ratio_milli, b=baseline_milli,
        )

    async def duel_list(self) -> dict:
        return await self._fn("public.crew_duel_list()")

    async def moments(self, week: date) -> dict:
        return await self._fn("public.crew_moments(cast(:w as date))", w=week)
