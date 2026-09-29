import os
from uuid import uuid4

# Must be set before app.config.get_settings() is ever called (it's called
# at app.main import time), so this happens at module import, before any
# `from app...` import below.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret-not-a-real-credential")

from cryptography.fernet import Fernet  # noqa: E402

os.environ.setdefault("FIELD_ENCRYPTION_KEY", Fernet.generate_key().decode())

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.deps import (  # noqa: E402
    get_checkin_repository,
    get_habit_repository,
    get_screen_time_repository,
    get_sleep_repository,
)
from app.main import app  # noqa: E402
from app.security import FieldEncryptor, get_current_user_id, get_field_encryptor  # noqa: E402

from tests.fakes import (  # noqa: E402
    InMemoryCheckinRepository,
    InMemoryHabitRepository,
    InMemoryScreenTimeRepository,
    InMemorySleepRepository,
)


class ApiWorld:
    """
    A shared pair of in-memory repositories (standing in for one Postgres
    database) plus a helper to mint a TestClient authenticated as any
    given user. This is what lets tests exercise real cross-user access
    control: two clients from the same world share the same underlying
    data, exactly like two users hitting the same deployed API would.
    """

    def __init__(self):
        self.habit_repo = InMemoryHabitRepository()
        self.checkin_repo = InMemoryCheckinRepository()
        self.sleep_repo = InMemorySleepRepository()
        self.screen_time_repo = InMemoryScreenTimeRepository()
        self.encryptor = FieldEncryptor(os.environ["FIELD_ENCRYPTION_KEY"])

        app.dependency_overrides[get_habit_repository] = lambda: self.habit_repo
        app.dependency_overrides[get_checkin_repository] = lambda: self.checkin_repo
        app.dependency_overrides[get_sleep_repository] = lambda: self.sleep_repo
        app.dependency_overrides[get_screen_time_repository] = lambda: self.screen_time_repo
        app.dependency_overrides[get_field_encryptor] = lambda: self.encryptor

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
