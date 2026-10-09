from __future__ import annotations

import base64
from uuid import UUID

from app.dates import Clock, utc_now
from app.repositories.account_repository import AccountRepository
from app.security import FieldEncryptor

_ENC_SUFFIX = "_encrypted"  # naming rule: journal_encrypted -> journal (+ journal_error)


class AccountService:
    def __init__(self, repo: AccountRepository, encryptor: FieldEncryptor, clock: Clock = utc_now):
        self._repo = repo
        self._encryptor = encryptor
        self._clock = clock

    async def export(self, user_id: UUID) -> dict:
        data = await self._repo.export(user_id)
        for rows in data.values():
            if not isinstance(rows, list):
                continue
            for row in rows:
                for col in [k for k in row if k.endswith(_ENC_SUFFIX)]:
                    raw = row.pop(col)
                    name = col[: -len(_ENC_SUFFIX)]
                    row[name], row[f"{name}_error"] = None, None
                    if raw is None:
                        continue
                    try:
                        row[name] = self._encryptor.decrypt(base64.b64decode(raw))
                    except ValueError:
                        # One bad row must never block the user from getting the rest of their data.
                        row[f"{name}_error"] = "undecryptable"
        return {"format_version": 1, "exported_at": self._clock().isoformat(), "data": data}

    async def delete_everything(self, user_id: UUID) -> dict[str, int]:
        return await self._repo.delete_everything(user_id)
