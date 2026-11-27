import os
import tempfile
from datetime import date, datetime

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from streamlit.testing.v1 import AppTest

from app.ai.handoff import generate_handoff_draft, render_handoff_draft
from app.db.models import Base, Project, Sprint, Task, User
from app.errors import NotFoundError, ValidationError
from app.services import (
    handoff_service,
    sprint_service,
    tasks_service,
    updates_service,
    users_service,
)
from app.services.handoff_service import get_handoffs, save_handoff
from app.services.tasks_service import create_task, get_task
from app.services.updates_service import add_update, get_task_history


SERVICE_MODULES = [
    tasks_service,
    updates_service,
    sprint_service,
    users_service,
    handoff_service,
]


def _run_tasks_updates_app():
    from app.ui.tasks_updates import render_tasks_updates

    render_tasks_updates()


def _select_task_in_app(at: AppTest, task_id: int) -> None:
    for sb in at.selectbox:
        if sb.label == "Select a task":
            matching = [opt for opt in sb.options if opt.startswith(f"T-{task_id} —")]
            assert matching, f"Task T-{task_id} not found in options: {sb.options}"
            sb.select(matching[0]).run()
            return
    raise AssertionError("Select a task selectbox not found")


# =========================================================
# 1. Draft Generation, Placeholders & Missing History
# =========================================================


def test_handoff_draft_filters_placeholders_and_deduplicates_facts(test_db):
    task = create_task(
        title="Handoff Deduplication Task",
        sprint_id=test_db["sprint_id"],
        assignee_id=test_db["user_id"],
        status="In Progress",
    )

    u1 = add_update(
        author_id=test_db["user_id"],
        task_id=task.id,
        entry_type="progress",
        completed_work="Built schema\nNone",
        remaining_work="N/A",
        blockers="Unknown",
        next_step="Not recorded",
    )
    u2 = add_update(
        author_id=test_db["user_id"],
        task_id=task.id,
        entry_type="progress",
        completed_work="built schema\nAdded migrations",
        remaining_work="Write docs",
        next_step="Open PR",
    )

    draft = generate_handoff_draft(task.id)
    assert draft.current_status == "In Progress"
    assert draft.completed_work == ["Built schema", "Added migrations"]
    assert draft.remaining_work == ["Write docs"]
    assert draft.blockers == []
    assert draft.decisions == []
    assert draft.next_steps == ["Open PR"]
    assert draft.source_ids == [f"T-{task.id}", f"U-{u1.id}", f"U-{u2.id}"]

    rendered = render_handoff_draft(draft)
    assert "Blockers:\n- Not recorded" in rendered
    assert "Decisions:\n- Not recorded" in rendered
    assert f"Sources: T-{task.id}, U-{u1.id}, U-{u2.id}" in rendered


def test_handoff_incomplete_history_renders_not_recorded_without_inventing(test_db):
    task = create_task(
        title="Sparse Task",
        sprint_id=test_db["sprint_id"],
        status="To Do",
    )

    draft = generate_handoff_draft(task.id)
    rendered = render_handoff_draft(draft)

    assert draft.completed_work == []
    assert draft.remaining_work == []
    assert draft.blockers == []
    assert draft.decisions == []
    assert draft.next_steps == []
    assert draft.source_ids == [f"T-{task.id}"]
    assert rendered.count("- Not recorded") == 5


# =========================================================
# 2. Validation, Invalid IDs & Non-Mutation Guarantees
# =========================================================


@pytest.mark.parametrize("bad_task_id", [0, -1, True, False, "1", None])
def test_generate_and_get_handoffs_reject_invalid_task_ids(test_db, bad_task_id):
    with pytest.raises(ValidationError):
        generate_handoff_draft(bad_task_id)

    with pytest.raises(ValidationError):
        get_handoffs(bad_task_id)


def test_generate_and_get_handoffs_reject_missing_task(test_db):
    with pytest.raises(NotFoundError):
        generate_handoff_draft(999999)

    with pytest.raises(NotFoundError):
        get_handoffs(999999)


def test_save_handoff_validates_task_author_content_and_sources(test_db):
    task_id = test_db["task_id"]
    user_id = test_db["user_id"]
    update_id = test_db["update_id"]

    # Invalid task_id / missing task
    with pytest.raises(ValidationError):
        save_handoff(0, user_id, "Content", [update_id])
    with pytest.raises(NotFoundError):
        save_handoff(999999, user_id, "Content", [update_id])

    # Invalid author_id / missing author
    with pytest.raises(ValidationError):
        save_handoff(task_id, True, "Content", [update_id])
    with pytest.raises(NotFoundError):
        save_handoff(task_id, 999999, "Content", [update_id])

    # Empty / non-string content
    for bad_content in ["", "   ", None, 123]:
        with pytest.raises(ValidationError):
            save_handoff(task_id, user_id, bad_content, [update_id])

    # Invalid source_update_ids shapes / duplicates / missing
    with pytest.raises(ValidationError):
        save_handoff(task_id, user_id, "Content", "not-a-list")
    with pytest.raises(ValidationError):
        save_handoff(task_id, user_id, "Content", [update_id, update_id])
    with pytest.raises(ValidationError):
        save_handoff(task_id, user_id, "Content", [0])
    with pytest.raises(NotFoundError):
        save_handoff(task_id, user_id, "Content", [999999])

    assert get_handoffs(task_id) == []


def test_generating_and_saving_handoff_do_not_mutate_task_or_updates(test_db):
    task_id = test_db["task_id"]
    before_task = get_task(task_id)
    before_history = get_task_history(task_id)

    draft = generate_handoff_draft(task_id)
    rendered = render_handoff_draft(draft)

    save_handoff(
        task_id=task_id,
        author_id=test_db["user_id"],
        content=rendered + "\nApproved.",
        source_update_ids=[test_db["update_id"]],
    )

    after_task = get_task(task_id)
    after_history = get_task_history(task_id)

    assert after_task.status == before_task.status
    assert after_task.assignee_id == before_task.assignee_id
    assert after_task.title == before_task.title
    assert after_task.description == before_task.description
    assert after_task.archived == before_task.archived
    assert after_task.updated_at == before_task.updated_at
    assert [(u.id, u.raw_text, u.completed_work) for u in after_history] == [
        (u.id, u.raw_text, u.completed_work) for u in before_history
    ]


# =========================================================
# 3. File-Backed Persistence Across New Session / Reconnect
# =========================================================


def test_saved_handoff_persists_across_engine_reconnection(monkeypatch):
    fd, tmp_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engines = []

    def connect():
        while engines:
            engines.pop().dispose()
        engine = create_engine(
            f"sqlite:///{tmp_path}",
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(engine, "connect")
        def fk_on(conn, _):
            cur = conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

        engines.append(engine)
        session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        import app.db.database as db_mod

        monkeypatch.setattr(db_mod, "SessionLocal", session_factory)
        for mod in SERVICE_MODULES:
            monkeypatch.setattr(mod, "SessionLocal", session_factory)
        return engine, session_factory

    try:
        engine, session_factory = connect()
        Base.metadata.create_all(bind=engine)

        with session_factory() as db:
            user = User(display_name="Reviewer", role="project_manager")
            project = Project(name="Handoff Persist", goal="Verify handoffs")
            db.add_all([user, project])
            db.flush()
            sprint = Sprint(
                project_id=project.id,
                goal="Handoff sprint",
                start_date=date(2026, 11, 1),
                end_date=date(2026, 11, 30),
                status="active",
            )
            db.add(sprint)
            db.flush()
            user_id = user.id
            sprint_id = sprint.id
            db.commit()

        task = create_task(
            title="API Handoff",
            sprint_id=sprint_id,
            assignee_id=user_id,
            status="In Progress",
        )
        u1 = add_update(
            author_id=user_id,
            task_id=task.id,
            entry_type="progress",
            completed_work="Finished auth middleware",
        )

        draft = generate_handoff_draft(task.id)
        approved_text = render_handoff_draft(draft) + "\nReviewed and approved."
        saved = save_handoff(
            task_id=task.id,
            author_id=user_id,
            content=approved_text,
            source_update_ids=[u1.id],
        )

        # Dispose engine and reconnect cleanly
        connect()
        loaded = get_handoffs(task.id)
        assert len(loaded) == 1
        assert loaded[0].id == saved.id
        assert loaded[0].task_id == task.id
        assert loaded[0].author_id == user_id
        assert loaded[0].status == "approved"
        assert loaded[0].source_update_ids == [u1.id]
        assert "Reviewed and approved." in loaded[0].content
        datetime.strptime(loaded[0].created_at, "%Y-%m-%dT%H:%M:%SZ")
    finally:
        while engines:
            engines.pop().dispose()
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# =========================================================
# 4. UI Handoff Review -> Approval -> Persistence (AppTest)
# =========================================================


def test_ui_handoff_requires_explicit_approval_and_saves_edited_content(test_db):
    task_id = test_db["task_id"]
    user_id = test_db["user_id"]
    update_id = test_db["update_id"]

    at = AppTest.from_function(_run_tasks_updates_app, default_timeout=15).run()
    _select_task_in_app(at, task_id)

    # Generate handoff draft — must NOT save yet
    next(b for b in at.button if b.label == "Generate Handoff Draft").click().run()
    assert get_handoffs(task_id) == []

    # Edit draft text without clicking "Approve and Save Handoff" — still NOT saved
    handoff_area = next(ta for ta in at.text_area if ta.key == f"handoff_content_{task_id}")
    assert f"Sources: T-{task_id}, U-{update_id}" in handoff_area.value
    handoff_area.input("Edited handoff summary ready for approval.").run()
    assert get_handoffs(task_id) == []

    # Approve and save edited handoff
    next(ta for ta in at.text_area if ta.key == f"handoff_content_{task_id}").input(
        "Edited handoff summary ready for approval."
    )
    next(b for b in at.button if b.label == "Approve and Save Handoff").click().run()

    assert not at.error, f"Unexpected UI errors: {[e.value for e in at.error]}"

    saved = get_handoffs(task_id)
    assert len(saved) == 1
    assert saved[0].task_id == task_id
    assert saved[0].author_id == user_id
    assert saved[0].status == "approved"
    assert saved[0].content == "Edited handoff summary ready for approval."
    assert saved[0].source_update_ids == [update_id]


def test_ui_handoff_rejects_empty_edited_content_without_saving(test_db):
    task_id = test_db["task_id"]

    at = AppTest.from_function(_run_tasks_updates_app, default_timeout=15).run()
    _select_task_in_app(at, task_id)

    next(b for b in at.button if b.label == "Generate Handoff Draft").click().run()
    next(ta for ta in at.text_area if ta.key == f"handoff_content_{task_id}").input("   ")
    next(b for b in at.button if b.label == "Approve and Save Handoff").click().run()

    assert any("Handoff content cannot be empty" in w.value for w in at.warning)
    assert get_handoffs(task_id) == []
