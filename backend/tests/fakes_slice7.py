from __future__ import annotations


class InMemoryLlmUsageRepository:
    def __init__(self):
        self.calls: dict[tuple, int] = {}
        self.tokens: dict[tuple, int] = {}

    async def consume(self, user_id, day, feature) -> int:
        key = (user_id, day, feature)
        self.calls[key] = self.calls.get(key, 0) + 1
        return self.total(user_id, day)

    async def release(self, user_id, day, feature) -> None:
        key = (user_id, day, feature)
        self.calls[key] = max(0, self.calls.get(key, 0) - 1)

    async def add_tokens(self, user_id, day, feature, tokens) -> None:
        key = (user_id, day, feature)
        self.tokens[key] = self.tokens.get(key, 0) + tokens

    def total(self, user_id, day) -> int:
        return sum(v for (u, d, _), v in self.calls.items() if u == user_id and d == day)
