
import pytest

from app.ai.handoff import (
    generate_handoff_draft,
    render_handoff_draft,
)
from app.errors import ValidationError
from app.services.handoff_service import (
    get_handoffs,
    save_handoff,
)
from app.services.tasks_service import create_task, get_task
from app.services.updates_service import add_update, get_task_history


def test_generate_handoff_draft_from_recorded_facts(test_db):
    add_update(
        author_id=test_db["user_id"],
        task_id=test_db["task_id"],
        entry_type="decision",
        content="Use SQLAlchemy for data access.",
        rationale="Keep services consistent.",
    )
    add_update(
        author_id=test_db["user_id"],
        task_id=test_db["task_id"],
        entry_type="blocker",
        blockers="Database connection issue.",
        next_step="Debug the connection.",
    )

    draft = generate_handoff_draft(test_db["task_id"])

    assert draft.current_status == "In Progress"
    assert "Initial implementation" in draft.completed_work
    assert (
        "Use SQLAlchemy for data access. "
        "(Rationale: Keep services consistent.)"
    ) in draft.decisions
    assert "Database connection issue." in draft.blockers
    assert "Debug the connection." in draft.next_steps
    assert f"T-{test_db['task_id']}" in draft.source_ids
    assert f"U-{test_db['update_id']}" in draft.source_ids


def test_generate_handoff_draft_leaves_missing_information_empty(test_db):
    task = create_task(
        title="Task without updates",
        sprint_id=test_db["sprint_id"],
    )

    draft = generate_handoff_draft(task.id)

    assert draft.current_status == "To Do"
    assert draft.completed_work == []
    assert draft.remaining_work == []
    assert draft.blockers == []
    assert draft.decisions == []
    assert draft.next_steps == []
    assert draft.source_ids == [f"T-{task.id}"]


def test_handoff_source_ids_match_task_history(test_db):
    history = get_task_history(test_db["task_id"])

    draft = generate_handoff_draft(test_db["task_id"])

    expected_ids = [f"T-{test_db['task_id']}"] + [
        f"U-{update.id}" for update in history
    ]

    assert draft.source_ids == expected_ids


def test_generating_handoff_does_not_change_task_state(test_db):
    before = get_task(test_db["task_id"])

    generate_handoff_draft(test_db["task_id"])

    after = get_task(test_db["task_id"])

    assert after.status == before.status
    assert after.assignee_id == before.assignee_id
    assert after.archived == before.archived
    assert after.updated_at == before.updated_at


def test_handoff_is_not_saved_before_approval(test_db):
    assert get_handoffs(test_db["task_id"]) == []

    generate_handoff_draft(test_db["task_id"])

    assert get_handoffs(test_db["task_id"]) == []


def test_save_handoff_persists_approved_reviewed_content(test_db):
    draft = generate_handoff_draft(test_db["task_id"])
    edited_content = (
        render_handoff_draft(draft)
        + "\nReviewer note: approved for handoff."
    )

    handoff = save_handoff(
        task_id=test_db["task_id"],
        author_id=test_db["user_id"],
        content=edited_content,
        source_update_ids=[test_db["update_id"]],
    )

    assert handoff.id is not None
    assert handoff.status == "approved"
    assert handoff.task_id == test_db["task_id"]
    assert handoff.author_id == test_db["user_id"]
    assert handoff.created_at
    assert handoff.source_update_ids == [test_db["update_id"]]
    assert "Reviewer note: approved for handoff." in handoff.content

    saved = get_handoffs(test_db["task_id"])

    assert len(saved) == 1
    assert saved[0].id == handoff.id


def test_save_handoff_rejects_sources_from_another_task(test_db):
    with pytest.raises(ValidationError):
        save_handoff(
            task_id=test_db["task_id"],
            author_id=test_db["user_id"],
            content="Invalid source mapping.",
            source_update_ids=[test_db["done_update_id"]],
        )
