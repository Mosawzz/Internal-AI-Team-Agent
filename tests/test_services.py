
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

def test_list_users_returns_list(test_db):
    users = list_users()

    assert isinstance(users, list)
    assert len(users) >= 1


def test_get_existing_user(test_db):
    user = get_user(test_db["user_id"])

    assert user.id == test_db["user_id"]
    assert user.display_name == "Test User"


def test_get_non_existing_user(test_db):
    with pytest.raises(NotFoundError):
        get_user(999999)


# -------------------------
# Tasks Service Tests
# -------------------------

def test_list_tasks_returns_list(test_db):
    tasks = list_tasks()

    assert isinstance(tasks, list)
    assert len(tasks) >= 1


def test_get_existing_task(test_db):
    task = get_task(test_db["task_id"])

    assert task.id == test_db["task_id"]
    assert task.title == "Test Task"


def test_get_non_existing_task(test_db):
    with pytest.raises(NotFoundError):
        get_task(999999)


def test_invalid_task_id():
    with pytest.raises(ValidationError):
        get_task(-1)


# -------------------------
# Updates Service Tests
# -------------------------

def test_task_history_returns_list(test_db):
    history = get_task_history(test_db["task_id"])

    assert isinstance(history, list)
    assert len(history) >= 1


def test_empty_history_for_task(test_db):
    """Create a task with no updates and verify empty history."""
    from app.services.tasks_service import create_task

    new_task = create_task(
        title="Task Without Updates",
        sprint_id=test_db["sprint_id"],
        assignee_id=test_db["user_id"],
    )

    assert get_task_history(new_task.id) == []


def test_search_updates_returns_list(test_db):
    results = search_updates("Initial")

    assert isinstance(results, list)


def test_invalid_search_limit():
    with pytest.raises(ValidationError):
        search_updates("database", limit=0)


# -------------------------
# Sprint Service Tests
# -------------------------

def test_sprint_summary(test_db):
    summary = get_sprint_summary()

    assert summary.sprint_id > 0
    assert isinstance(summary.counts, dict)
    assert isinstance(summary.blocked_tasks, list)


# -------------------------
# Handoff Service Tests
# -------------------------

def test_get_handoffs_returns_list(test_db):
    handoffs = get_handoffs(test_db["task_id"])

    assert isinstance(handoffs, list)


def test_get_handoffs_for_missing_task(test_db):
    with pytest.raises(NotFoundError):
        get_handoffs(999999)
