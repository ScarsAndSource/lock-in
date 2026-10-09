from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID, uuid4

from app.domain import Goal, GoalStatus, Intention, StudySession, Subject, UrgeLog
from app.exceptions import ConflictError


class InMemorySubjectRepository:
    def __init__(self):
        self._subjects: dict[UUID, Subject] = {}

    async def create(self, user_id: UUID, name: str) -> Subject | None:
        norm = name.strip().lower()
        for s in self._subjects.values():
            if s.user_id == user_id and s.name.strip().lower() == norm and s.archived_at is None:
                return None
        subject = Subject(id=uuid4(), user_id=user_id, name=name.strip(), created_at=datetime.now(timezone.utc))
        self._subjects[subject.id] = subject
        return subject

    async def find_by_name(self, user_id: UUID, name: str) -> Subject | None:
        norm = name.strip().lower()
        active = [s for s in self._subjects.values() if s.user_id == user_id and s.name.strip().lower() == norm and s.archived_at is None]
        if active:
            return active[0]
        archived = [s for s in self._subjects.values() if s.user_id == user_id and s.name.strip().lower() == norm]
        return archived[0] if archived else None

    async def list(self, user_id: UUID, include_archived: bool = False) -> list[Subject]:
        return sorted(
            [s for s in self._subjects.values() if s.user_id == user_id and (include_archived or s.archived_at is None)],
            key=lambda s: s.name.lower(),
        )

    async def get(self, user_id: UUID, subject_id: UUID) -> Subject | None:
        s = self._subjects.get(subject_id)
        return s if s is not None and s.user_id == user_id else None

    async def update(self, user_id: UUID, subject_id: UUID, name: str | None, archived: bool | None, now: datetime) -> Subject | None:
        s = await self.get(user_id, subject_id)
        if s is None:
            return None
        if name is not None:
            norm = name.strip().lower()
            for other in self._subjects.values():
                if other.user_id == user_id and other.id != subject_id and other.name.strip().lower() == norm and other.archived_at is None:
                    raise ConflictError("You already have a subject with that name.")
            s.name = name.strip()
        if archived is True:
            s.archived_at = now
        elif archived is False:
            s.archived_at = None
        return s


class InMemoryStudySessionRepository:
    def __init__(self):
        self._sessions: dict[UUID, StudySession] = {}

    async def add(self, session: StudySession) -> StudySession:
        self._sessions[session.id] = session
        return session

    async def get(self, user_id: UUID, session_id: UUID) -> StudySession | None:
        s = self._sessions.get(session_id)
        return s if s is not None and s.user_id == user_id else None

    async def list_in_range(self, user_id: UUID, start_date: date, end_date: date) -> list[StudySession]:
        return [
            s for s in self._sessions.values()
            if s.user_id == user_id and start_date <= s.log_date <= end_date
        ]

    async def list_by_subject(self, user_id: UUID, subject_id: UUID) -> list[StudySession]:
        return [
            s for s in self._sessions.values()
            if s.user_id == user_id and s.subject_id == subject_id
        ]

    async def delete(self, user_id: UUID, session_id: UUID) -> bool:
        s = self._sessions.get(session_id)
        if s is None or s.user_id != user_id:
            return False
        del self._sessions[session_id]
        return True


class InMemoryUrgeRepository:
    def __init__(self):
        self._logs: dict[UUID, UrgeLog] = {}

    async def add(self, log: UrgeLog) -> UrgeLog:
        self._logs[log.id] = log
        return log

    async def get(self, user_id: UUID, urge_id: UUID) -> UrgeLog | None:
        l = self._logs.get(urge_id)
        return l if l is not None and l.user_id == user_id else None

    async def update_detail(self, user_id: UUID, urge_id: UUID, changes: dict) -> UrgeLog | None:
        l = await self.get(user_id, urge_id)
        if l is None:
            return None
        for col, val in changes.items():
            setattr(l, col, val)
        return l

    async def delete(self, user_id: UUID, urge_id: UUID) -> bool:
        l = self._logs.get(urge_id)
        if l is None or l.user_id != user_id:
            return False
        del self._logs[urge_id]
        return True

    async def list_in_range(self, user_id: UUID, start_date: date, end_date: date) -> list[UrgeLog]:
        return sorted(
            [l for l in self._logs.values() if l.user_id == user_id and start_date <= l.log_date <= end_date],
            key=lambda l: l.occurred_at,
        )

    async def list_recent(self, user_id: UUID, limit: int = 50) -> list[UrgeLog]:
        return sorted(
            [l for l in self._logs.values() if l.user_id == user_id],
            key=lambda l: l.occurred_at, reverse=True,
        )[:limit]


class InMemoryGoalRepository:
    def __init__(self):
        self._goals: dict[UUID, Goal] = {}

    async def create(self, goal: Goal) -> Goal:
        self._goals[goal.id] = goal
        return goal

    async def count_active(self, user_id: UUID) -> int:
        return sum(1 for g in self._goals.values() if g.user_id == user_id and g.status == GoalStatus.ACTIVE)

    async def list(self, user_id: UUID, status: GoalStatus | None = None) -> list[Goal]:
        return [
            g for g in self._goals.values()
            if g.user_id == user_id and (status is None or g.status == status)
        ]

    async def list_active_by_domain(self, user_id: UUID, domain: str) -> list[Goal]:
        return [
            g for g in self._goals.values()
            if g.user_id == user_id and g.domain == domain and g.status == GoalStatus.ACTIVE
        ]

    async def get(self, user_id: UUID, goal_id: UUID) -> Goal | None:
        g = self._goals.get(goal_id)
        return g if g is not None and g.user_id == user_id else None

    async def update(self, user_id: UUID, goal_id: UUID, definition: str | None, status: GoalStatus | None, target: dict | None, now: datetime) -> Goal | None:
        g = await self.get(user_id, goal_id)
        if g is None:
            return None
        if definition is not None:
            g.definition = definition
        if status is not None:
            g.status = status
        if target is not None:
            g.target = target
        return g

    async def delete(self, user_id: UUID, goal_id: UUID) -> bool:
        g = await self.get(user_id, goal_id)
        if g is None:
            return False
        del self._goals[goal_id]
        return True


class InMemoryIntentionRepository:
    def __init__(self):
        self._intentions: dict[UUID, Intention] = {}

    async def create(self, intention: Intention) -> Intention:
        self._intentions[intention.id] = intention
        return intention

    async def count_active(self, user_id: UUID) -> int:
        return sum(1 for i in self._intentions.values() if i.user_id == user_id and i.active)

    async def list(self, user_id: UUID, domain: str | None = None, active_only: bool = False) -> list[Intention]:
        return [
            i for i in self._intentions.values()
            if i.user_id == user_id and (domain is None or i.linked_domain == domain) and (not active_only or i.active)
        ]

    async def get(self, user_id: UUID, intention_id: UUID) -> Intention | None:
        i = self._intentions.get(intention_id)
        return i if i is not None and i.user_id == user_id else None

    async def update(self, user_id: UUID, intention_id: UUID, cue: str | None, action: str | None, active: bool | None, now: datetime) -> Intention | None:
        i = await self.get(user_id, intention_id)
        if i is None:
            return None
        if cue is not None:
            i.cue = cue
        if action is not None:
            i.action = action
        if active is not None:
            i.active = active
        return i

    async def delete(self, user_id: UUID, intention_id: UUID) -> bool:
        i = await self.get(user_id, intention_id)
        if i is None:
            return False
        del self._intentions[intention_id]
        return True
