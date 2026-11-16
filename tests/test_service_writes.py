
import pytest

from app.errors import ValidationError

from app.services.tasks_service import (
    create_task,
    update_task,
    get_task,
    archive_task,
)

from app.services.updates_service import (
    add_update,
    get_task_history,
)

from app.services.handoff_service import (
    save_handoff,
    get_handoffs,
)


# -------------------------
# Create Task Tests
# -------------------------

def test_create_task(test_db):

    task = create_task(
        title="New Test Task",
        sprint_id=test_db["sprint_id"],
        assignee_id=test_db["user_id"],
    )

    assert task.id is not None
    assert task.title == "New Test Task"
    assert task.status == "To Do"


def test_create_task_with_invalid_status(test_db):

    with pytest.raises(ValidationError):
        create_task(
            title="Invalid Task",
            sprint_id=test_db["sprint_id"],
            status="Invalid Status",
        )


# -------------------------
# Update Task Tests
# -------------------------

def test_update_task(test_db):

    task = update_task(
        task_id=test_db["task_id"],
        title="Updated Test Task",
        status="Blocked",
    )

    assert task.title == "Updated Test Task"
    assert task.status == "Blocked"


# -------------------------
# Add Update Tests
# -------------------------

def test_add_update(test_db):

    update = add_update(
        author_id=test_db["user_id"],
        task_id=test_db["task_id"],
        entry_type="progress",
        completed_work="Implemented test feature",
        next_step="Continue testing",
    )

    assert update.id is not None
    assert update.task_id == test_db["task_id"]

    history = get_task_history(test_db["task_id"])

    assert any(item.id == update.id for item in history)


# -------------------------
# Archive Tests
# -------------------------

def test_archive_done_task(test_db):

    task = archive_task(test_db["done_task_id"])

    assert task.archived is True
    assert task.status == "Done"


def test_cannot_archive_incomplete_task(test_db):

    with pytest.raises(ValidationError):
        archive_task(test_db["task_id"])


def test_archive_does_not_delete_updates(test_db):

    task_id = test_db["done_task_id"]
    update_id = test_db["done_update_id"]

    archive_task(task_id)

    history = get_task_history(task_id)

    assert any(item.id == update_id for item in history)


# -------------------------
# Handoff Tests
# -------------------------

def test_save_handoff(test_db):

    handoff = save_handoff(
        task_id=test_db["task_id"],
        author_id=test_db["user_id"],
        content="Task progress and remaining work summary.",
        source_update_ids=[test_db["update_id"]],
    )

    assert handoff.id is not None
    assert handoff.status == "approved"
    assert handoff.task_id == test_db["task_id"]


def test_get_handoffs(test_db):

    save_handoff(
        task_id=test_db["task_id"],
        author_id=test_db["user_id"],
        content="Test handoff content",
        source_update_ids=[test_db["update_id"]],
    )

    handoffs = get_handoffs(test_db["task_id"])

    assert len(handoffs) == 1
    assert handoffs[0].status == "approved"
