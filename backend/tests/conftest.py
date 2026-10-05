import os
from datetime import datetime, timezone
from uuid import uuid4

# Must be set before app.config.get_settings() is first called (at app.main import).
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret-not-a-real-credential")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("SCHEMA_CHECK_MODE", "off")

from cryptography.fernet import Fernet  # noqa: E402

os.environ.setdefault("FIELD_ENCRYPTION_KEY", Fernet.generate_key().decode())

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.deps import (  # noqa: E402
    get_account_repository, get_checkin_repository, get_clock, get_habit_repository,
    get_mission_repository, get_profile_repository, get_screen_time_repository, get_sleep_repository,
)
from app.main import app  # noqa: E402
from app.security import FieldEncryptor, get_current_user_id, get_field_encryptor  # noqa: E402

from tests.fakes import (  # noqa: E402
    InMemoryAccountRepository, InMemoryCheckinRepository, InMemoryHabitRepository,
    InMemoryMissionRepository, InMemoryProfileRepository, InMemoryScreenTimeRepository,
    InMemorySleepRepository,
)

FIXED_NOW = datetime(2026, 12, 31, 12, 0, tzinfo=timezone.utc)


class ApiWorld:
    """One shared fake 'database' + a controllable clock. client_as() sets the
    authenticated user GLOBALLY -- call it right before each user's requests."""

    def __init__(self):
        self.now = FIXED_NOW
        self.habit_repo = InMemoryHabitRepository()
        self.checkin_repo = InMemoryCheckinRepository()
        self.sleep_repo = InMemorySleepRepository()
        self.screen_time_repo = InMemoryScreenTimeRepository()
        self.profile_repo = InMemoryProfileRepository()
        self.mission_repo = InMemoryMissionRepository()
        self.account_repo = InMemoryAccountRepository(
            self.habit_repo, self.checkin_repo, self.sleep_repo,
            self.screen_time_repo, self.mission_repo, self.profile_repo,
        )
        self.encryptor = FieldEncryptor(os.environ["FIELD_ENCRYPTION_KEY"])
        self._clock = lambda: self.now

        app.dependency_overrides[get_habit_repository] = lambda: self.habit_repo
        app.dependency_overrides[get_checkin_repository] = lambda: self.checkin_repo
        app.dependency_overrides[get_sleep_repository] = lambda: self.sleep_repo
        app.dependency_overrides[get_screen_time_repository] = lambda: self.screen_time_repo
        app.dependency_overrides[get_profile_repository] = lambda: self.profile_repo
        app.dependency_overrides[get_mission_repository] = lambda: self.mission_repo
        app.dependency_overrides[get_account_repository] = lambda: self.account_repo
        app.dependency_overrides[get_field_encryptor] = lambda: self.encryptor
        app.dependency_overrides[get_clock] = lambda: self._clock

    def client_as(self, user_id) -> TestClient:
        app.dependency_overrides[get_current_user_id] = lambda: user_id
        return TestClient(app)


@pytest.fixture
def world():
    world = ApiWorld()
    yield world
    app.dependency_overrides.clear()


@pytest.fixture
def user_a():
    return uuid4()


@pytest.fixture
def user_b():
    return uuid4()
