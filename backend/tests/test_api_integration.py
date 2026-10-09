from datetime import date, timedelta


def _create_habit(client, name="Gym", frequency=None):
    resp = client.post(
        "/habits",
        json={
            "name": name,
            "target_frequency": frequency or {"type": "n_per_week", "count": 5},
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_create_and_list_habit(world, user_a):
    client = world.client_as(user_a)

    created = _create_habit(client)
    assert created["name"] == "Gym"
    assert created["archived_at"] is None

    listed = client.get("/habits").json()
    assert len(listed) == 1
    assert listed[0]["id"] == created["id"]


def test_new_habit_checkin_default_is_done_and_low_confidence(world, user_a):
    client = world.client_as(user_a)
    habit = _create_habit(client)
    today = date(2026, 9, 27)

    resp = client.get(f"/checkins/{today.isoformat()}/defaults")
    assert resp.status_code == 200
    entries = resp.json()["entries"]

    assert len(entries) == 1
    assert entries[0]["habit_id"] == habit["id"]
    assert entries[0]["status"] == "done"
    assert entries[0]["is_default"] is True
    assert entries[0]["is_low_confidence"] is True
    assert resp.json()["already_confirmed"] is False


def test_confirm_without_override_persists_the_proposed_default(world, user_a):
    client = world.client_as(user_a)
    habit = _create_habit(client)
    today = date(2026, 9, 27)

    resp = client.post(f"/checkins/{today.isoformat()}/confirm", json={})
    assert resp.status_code == 200
    entry = resp.json()["entries"][0]
    assert entry["status"] == "done"
    assert entry["is_default"] is True

    # Re-fetching defaults for the same date should now report the real
    # logged entry, not propose a fresh default over it.
    view = client.get(f"/checkins/{today.isoformat()}/defaults").json()
    assert view["already_confirmed"] is True
    assert view["entries"][0]["reason"] == "Already logged for this date."


def test_confirm_with_override_is_not_marked_as_default(world, user_a):
    client = world.client_as(user_a)
    habit = _create_habit(client)
    today = date(2026, 9, 27)

    resp = client.post(
        f"/checkins/{today.isoformat()}/confirm",
        json={"overrides": [{"habit_id": habit["id"], "status": "skipped", "note": "sick"}]},
    )
    assert resp.status_code == 200
    entry = resp.json()["entries"][0]
    assert entry["status"] == "skipped"
    assert entry["is_default"] is False


def test_journal_text_is_encrypted_at_rest(world, user_a):
    client = world.client_as(user_a)
    today = date(2026, 9, 27)
    secret_text = "felt the urge after a bad night's sleep, used the if-then plan and resisted"

    client.post(f"/checkins/{today.isoformat()}/confirm", json={"journal_text": secret_text})

    stored = world.checkin_repo._checkins[(user_a, today)]
    assert stored.journal_encrypted is not None
    assert secret_text.encode() not in stored.journal_encrypted
    assert world.encryptor.decrypt(stored.journal_encrypted) == secret_text


def test_user_cannot_log_against_another_users_habit(world, user_a, user_b):
    client_a = world.client_as(user_a)
    habit = _create_habit(client_a)

    client_b = world.client_as(user_b)
    resp = client_b.post(
        f"/habits/{habit['id']}/logs",
        json={"log_date": "2026-09-27", "status": "done"},
    )
    assert resp.status_code == 404


def test_user_cannot_see_another_users_habits(world, user_a, user_b):
    client_a = world.client_as(user_a)
    _create_habit(client_a)

    client_b = world.client_as(user_b)
    assert client_b.get("/habits").json() == []


def test_confirm_rejects_override_for_unknown_habit(world, user_a):
    import uuid

    client = world.client_as(user_a)
    resp = client.post(
        "/checkins/2026-09-27/confirm",
        json={"overrides": [{"habit_id": str(uuid.uuid4()), "status": "done"}]},
    )
    assert resp.status_code == 404


def test_confirm_rejects_duplicate_habit_id_in_overrides(world, user_a):
    client = world.client_as(user_a)
    habit = _create_habit(client)

    resp = client.post(
        "/checkins/2026-09-27/confirm",
        json={
            "overrides": [
                {"habit_id": habit["id"], "status": "done"},
                {"habit_id": habit["id"], "status": "skipped"},
            ]
        },
    )
    assert resp.status_code == 422


def test_correcting_a_past_default_after_the_fact(world, user_a):
    """
    SPEC.md section 8: 'a default gets it wrong' -- there needs to be a way
    to correct it after the fact, not just before. Logging directly against
    a past date is that mechanism.
    """
    client = world.client_as(user_a)
    habit = _create_habit(client)
    yesterday = date(2026, 9, 26)

    # Confirm yesterday with the (optimistic) default of "done".
    client.post(f"/checkins/{yesterday.isoformat()}/confirm", json={})

    # Turns out that was wrong -- correct it directly via /habits/{id}/logs.
    resp = client.post(
        f"/habits/{habit['id']}/logs",
        json={"log_date": yesterday.isoformat(), "status": "skipped", "note": "was actually sick"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "skipped"
    assert resp.json()["is_default"] is False


def test_history_influences_tomorrows_default(world, user_a):
    client = world.client_as(user_a)
    habit = _create_habit(client)
    thursday = date(2026, 9, 24)

    # Three consecutive Thursdays, all confirmed as "skipped" via override (real logs).
    for i in range(3):
        d = thursday - timedelta(weeks=2 - i)
        client.post(
            f"/checkins/{d.isoformat()}/confirm",
            json={"overrides": [{"habit_id": habit["id"], "status": "skipped"}]},
        )

    next_thursday = thursday + timedelta(weeks=1)
    view = client.get(f"/checkins/{next_thursday.isoformat()}/defaults").json()

    assert view["entries"][0]["status"] == "skipped"
    assert view["entries"][0]["is_low_confidence"] is False


def test_confirming_defaults_does_not_turn_guesses_into_history(world, user_a):
    """Confirming defaults without overrides writes is_default=True, which never feeds into future defaults."""
    client = world.client_as(user_a)
    habit = _create_habit(client)
    thursday = date(2026, 9, 24)

    # Confirm defaults without overrides on 3 Thursdays
    for i in range(3):
        d = thursday - timedelta(weeks=2 - i)
        client.post(f"/checkins/{d.isoformat()}/confirm", json={})

    next_thursday = thursday + timedelta(weeks=1)
    view = client.get(f"/checkins/{next_thursday.isoformat()}/defaults").json()

    # Guesses were ignored, so occurrence count remains 0 -> stays low confidence
    assert view["entries"][0]["is_low_confidence"] is True
