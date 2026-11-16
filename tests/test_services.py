
import pytest

from app.errors import ValidationError, NotFoundError

from app.services.tasks_service import (
    list_tasks,
    get_task,
)

from app.services.updates_service import (
    get_task_history,
    search_updates,
)

from app.services.sprint_service import get_sprint_summary

from app.services.users_service import (
    list_users,
    get_user,
)

from app.services.handoff_service import get_handoffs


# -------------------------
# Users Service Tests
# -------------------------

def test_list_users_returns_list():
    users = list_users()

    assert isinstance(users, list)


def test_get_existing_user():
    users = list_users()

    if not users:
        pytest.skip("No seeded users found.")

    user = get_user(users[0].id)

    assert user.id == users[0].id


def test_get_non_existing_user():
    with pytest.raises(NotFoundError):
        get_user(999999)


# -------------------------
# Tasks Service Tests
# -------------------------

def test_list_tasks_returns_list():
    tasks = list_tasks()

    assert isinstance(tasks, list)


def test_get_existing_task():
    tasks = list_tasks()

    if not tasks:
        pytest.skip("No seeded tasks found.")

    task = get_task(tasks[0].id)

    assert task.id == tasks[0].id


def test_get_non_existing_task():
    with pytest.raises(NotFoundError):
        get_task(999999)


def test_invalid_task_id():
    with pytest.raises(ValidationError):
        get_task(-1)


# -------------------------
# Updates Service Tests
# -------------------------

def test_task_history_returns_list():
    tasks = list_tasks()

    if not tasks:
        pytest.skip("No seeded tasks found.")

    history = get_task_history(tasks[0].id)

    assert isinstance(history, list)


def test_empty_history_for_task():
    tasks = list_tasks()

    if not tasks:
        pytest.skip("No seeded tasks found.")

    # Use a task with no updates if one exists
    task_without_updates = None

    for task in tasks:
        if not get_task_history(task.id):
            task_without_updates = task
            break

    if task_without_updates is None:
        pytest.skip("All seeded tasks already have updates.")

    assert get_task_history(task_without_updates.id) == []


def test_search_updates_returns_list():
    results = search_updates("database")

    assert isinstance(results, list)


def test_invalid_search_limit():
    with pytest.raises(ValidationError):
        search_updates("database", limit=0)


# -------------------------
# Sprint Service Tests
# -------------------------

def test_sprint_summary():
    summary = get_sprint_summary()

    assert summary.sprint_id > 0
    assert isinstance(summary.counts, dict)
    assert isinstance(summary.blocked_tasks, list)


# -------------------------
# Handoff Service Tests
# -------------------------

def test_get_handoffs_returns_list():
    tasks = list_tasks()

    if not tasks:
        pytest.skip("No seeded tasks found.")

    handoffs = get_handoffs(tasks[0].id)

    assert isinstance(handoffs, list)


def test_get_handoffs_for_missing_task():
    with pytest.raises(NotFoundError):
        get_handoffs(999999)
