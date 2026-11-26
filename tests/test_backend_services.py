import os
import tempfile
from datetime import date

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, Handoff, Project, Sprint, Task, Update, User
from app.errors import NotFoundError, ValidationError
from app.services import (
    handoff_service,
    sprint_service,
    tasks_service,
    updates_service,
    users_service,
)
from app.services.handoff_service import get_handoffs, save_handoff
from app.services.sprint_service import get_sprint_summary
from app.services.tasks_service import (
    archive_task,
    create_task,
    get_task,
    list_tasks,
    update_task,
)
from app.services.updates_service import add_update, get_task_history, search_updates
from app.services.users_service import get_user, list_users


SERVICE_MODULES = [
    tasks_service,
    updates_service,
    sprint_service,
    users_service,
    handoff_service,
]


def _make_file_sessionmaker(db_path: str):
    """Create a fresh SQLAlchemy engine and sessionmaker for a SQLite file."""
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )
    return engine, session_factory


def _patch_service_sessions(monkeypatch, session_factory):
    """Point database and all service modules at the given sessionmaker."""
    import app.db.database as db_mod

    monkeypatch.setattr(db_mod, "SessionLocal", session_factory)
    for module in SERVICE_MODULES:
        monkeypatch.setattr(module, "SessionLocal", session_factory)


@pytest.fixture
def file_db(monkeypatch):
    """Provide an isolated, file-backed SQLite database with reconnect support."""
    fd, tmp_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    engines = []

    def open_connection():
        while engines:
            engines.pop().dispose()
        engine, session_factory = _make_file_sessionmaker(tmp_path)
        engines.append(engine)
        _patch_service_sessions(monkeypatch, session_factory)
        return engine, session_factory

    engine, session_factory = open_connection()
    Base.metadata.create_all(bind=engine)

    with session_factory() as db:
        user1 = User(display_name="Primary User", role="team_member")
        user2 = User(display_name="Second User", role="project_manager")
        project = Project(name="Persistence Project", goal="Verify DB persistence")
        db.add_all([user1, user2, project])
        db.flush()

        sprint = Sprint(
            project_id=project.id,
            goal="Stage 5 persistence sprint",
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 30),
            status="active",
        )
        db.add(sprint)
        db.flush()

        seed_ids = {
            "user1_id": user1.id,
            "user2_id": user2.id,
            "project_id": project.id,
            "sprint_id": sprint.id,
            "db_path": tmp_path,
            "reconnect": open_connection,
        }
        db.commit()

    yield seed_ids

    for eng in engines:
        eng.dispose()
    try:
        os.unlink(tmp_path)
    except OSError:
        pass


# =========================================================
# Task A: Task, Update, User, and Validation Services
# =========================================================


def test_task_creation_all_valid_statuses_and_title_trimming(test_db):
    created = []
    for status in ["To Do", "In Progress", "Blocked", "Done"]:
        task = create_task(
            title=f"  Task {status}  ",
            sprint_id=test_db["sprint_id"],
            description="Details",
            assignee_id=test_db["user_id"],
            status=status,
        )
        created.append(task)
        assert task.title == f"Task {status}"
        assert task.status == status

    assert len(created) == 4


@pytest.mark.parametrize("bad_title", ["", "   ", None, 123])
def test_create_task_rejects_invalid_title(test_db, bad_title):
    before_count = len(list_tasks(include_archived=True))
    with pytest.raises(ValidationError):
        create_task(title=bad_title, sprint_id=test_db["sprint_id"])
    assert len(list_tasks(include_archived=True)) == before_count


@pytest.mark.parametrize("bad_id", [0, -5, True, "1", None])
def test_create_task_rejects_invalid_sprint_id(test_db, bad_id):
    with pytest.raises(ValidationError):
        create_task(title="Valid Title", sprint_id=bad_id)


def test_create_task_missing_foreign_keys_leave_no_partial_record(test_db):
    before_count = len(list_tasks(include_archived=True))

    with pytest.raises(NotFoundError):
        create_task(title="No Sprint", sprint_id=999999)

    with pytest.raises(NotFoundError):
        create_task(
            title="No Assignee",
            sprint_id=test_db["sprint_id"],
            assignee_id=999999,
        )

    assert len(list_tasks(include_archived=True)) == before_count


def test_list_tasks_filtering_and_validation(test_db):
    t1 = create_task(
        title="Filter To Do",
        sprint_id=test_db["sprint_id"],
        assignee_id=test_db["user_id"],
        status="To Do",
    )
    t2 = create_task(
        title="Filter Blocked",
        sprint_id=test_db["sprint_id"],
        assignee_id=None,
        status="Blocked",
    )

    todo_tasks = list_tasks(status="To Do")
    assert any(t.id == t1.id for t in todo_tasks)
    assert all(t.status == "To Do" for t in todo_tasks)

    user_tasks = list_tasks(assignee_id=test_db["user_id"])
    assert any(t.id == t1.id for t in user_tasks)
    assert all(t.id != t2.id for t in user_tasks)

    with pytest.raises(ValidationError):
        list_tasks(status="Unknown")
    with pytest.raises(ValidationError):
        list_tasks(include_archived="yes")
    with pytest.raises(ValidationError):
        list_tasks(assignee_id=0)


def test_update_task_validation_and_atomic_failure(test_db):
    task_id = test_db["task_id"]
    original = get_task(task_id)

    # Unsupported field rejected
    with pytest.raises(ValidationError):
        update_task(task_id, archived=True)

    # Invalid description type rejected
    with pytest.raises(ValidationError):
        update_task(task_id, description=12345)

    # Nonexistent assignee leaves task unchanged
    with pytest.raises(NotFoundError):
        update_task(task_id, title="Should Not Persist", assignee_id=999999)

    after_fail = get_task(task_id)
    assert after_fail.title == original.title
    assert after_fail.assignee_id == original.assignee_id

    # Nonexistent task
    with pytest.raises(NotFoundError):
        update_task(999999, title="Ghost")

    # Unassigning with None succeeds
    unassigned = update_task(task_id, assignee_id=None)
    assert unassigned.assignee_id is None


def test_add_update_validation_and_failed_write_atomicity(test_db):
    task_id = test_db["task_id"]
    before_history = get_task_history(task_id)

    with pytest.raises(ValidationError):
        add_update(author_id=test_db["user_id"], task_id=task_id, entry_type="invalid")

    with pytest.raises(ValidationError):
        add_update(
            author_id=test_db["user_id"],
            task_id=task_id,
            entry_type="progress",
            completed_work=42,
        )

    with pytest.raises(NotFoundError):
        add_update(
            author_id=999999,
            task_id=task_id,
            entry_type="note",
            raw_text="Missing author",
        )

    with pytest.raises(NotFoundError):
        add_update(
            author_id=test_db["user_id"],
            task_id=999999,
            entry_type="note",
            raw_text="Missing task",
        )

    assert len(get_task_history(task_id)) == len(before_history)

    # Task-independent general update (task_id=None) is allowed
    general = add_update(
        author_id=test_db["user_id"],
        task_id=None,
        entry_type="decision",
        content="Use SQLite for local dev",
        rationale="Zero external DB setup",
    )
    assert general.id is not None
    assert general.task_id is None


def test_user_and_sprint_validation(test_db):
    users = list_users()
    assert len(users) == 1
    assert get_user(test_db["user_id"]).id == test_db["user_id"]

    with pytest.raises(ValidationError):
        get_user(True)
    with pytest.raises(ValidationError):
        get_user(0)
    with pytest.raises(ValidationError):
        get_sprint_summary(sprint_id=-1)
    with pytest.raises(NotFoundError):
        get_sprint_summary(sprint_id=999999)


# =========================================================
# Task B: History Ordering, Relationships, and Edge Cases
# =========================================================


def test_history_multiple_updates_ordering_and_relationships(test_db):
    task = create_task(
        title="Multi-update Task",
        sprint_id=test_db["sprint_id"],
        assignee_id=test_db["user_id"],
    )

    u1 = add_update(
        author_id=test_db["user_id"],
        task_id=task.id,
        entry_type="progress",
        completed_work="Step 1",
    )
    u2 = add_update(
        author_id=test_db["user_id"],
        task_id=task.id,
        entry_type="blocker",
        blockers="Waiting on review",
    )
    u3 = add_update(
        author_id=test_db["user_id"],
        task_id=task.id,
        entry_type="decision",
        content="Proceed with option A",
    )

    history = get_task_history(task.id)
    assert [u.id for u in history] == [u1.id, u2.id, u3.id]
    assert all(u.task_id == task.id for u in history)
    assert all(u.author_id == test_db["user_id"] for u in history)


def test_history_missing_and_invalid_task_ids(test_db):
    with pytest.raises(NotFoundError):
        get_task_history(999999)

    for bad_id in [0, -1, True, "12"]:
        with pytest.raises(ValidationError):
            get_task_history(bad_id)


# =========================================================
# Task C: Archive Rules, Retention, and Listing Behavior
# =========================================================


@pytest.mark.parametrize("incomplete_status", ["To Do", "In Progress", "Blocked"])
def test_cannot_archive_any_incomplete_status(test_db, incomplete_status):
    task = create_task(
        title=f"Incomplete {incomplete_status}",
        sprint_id=test_db["sprint_id"],
        status=incomplete_status,
    )

    with pytest.raises(ValidationError):
        archive_task(task.id)

    reloaded = get_task(task.id)
    assert reloaded.archived is False
    assert reloaded.status == incomplete_status


def test_archive_retains_task_updates_and_handoffs_and_updates_listings(test_db):
    done_id = test_db["done_task_id"]
    done_update_id = test_db["done_update_id"]

    handoff = save_handoff(
        task_id=done_id,
        author_id=test_db["user_id"],
        content="Final handoff before archiving.",
        source_update_ids=[done_update_id],
    )

    archived = archive_task(done_id)
    assert archived.archived is True
    assert archived.status == "Done"

    # Task remains retrievable by ID
    stored = get_task(done_id)
    assert stored.archived is True

    # Updates and handoffs remain intact
    history = get_task_history(done_id)
    assert any(u.id == done_update_id for u in history)

    handoffs = get_handoffs(done_id)
    assert len(handoffs) == 1
    assert handoffs[0].id == handoff.id

    # Active listing excludes archived; include_archived=True includes it
    active_ids = {t.id for t in list_tasks()}
    all_ids = {t.id for t in list_tasks(include_archived=True)}
    assert done_id not in active_ids
    assert done_id in all_ids

    # Sprint summary excludes archived Done task
    summary = get_sprint_summary(test_db["sprint_id"])
    assert summary.counts["Done"] == 0


# =========================================================
# Task D: File-Backed SQLite Persistence & Rollback
# =========================================================


def test_persistence_across_session_and_engine_reconnection(file_db):
    reconnect = file_db["reconnect"]

    # 1. Create and commit a task, then reconnect with a new engine/session
    created_task = create_task(
        title="Persisted Task",
        sprint_id=file_db["sprint_id"],
        description="Must survive engine disposal",
        assignee_id=file_db["user1_id"],
        status="In Progress",
    )

    old_engine, _ = reconnect()
    # Reconnect again after disposing to simulate fresh process startup
    # (note: file_db fixture disposes all tracked engines at teardown)
    persisted_task = get_task(created_task.id)
    assert persisted_task.title == "Persisted Task"
    assert persisted_task.status == "In Progress"
    assert persisted_task.assignee_id == file_db["user1_id"]

    # 2. Commit an update and retrieve through a fresh connection
    created_update = add_update(
        author_id=file_db["user2_id"],
        task_id=created_task.id,
        entry_type="progress",
        completed_work="Persistence verified",
        next_step="Update task status",
    )

    reconnect()
    history = get_task_history(created_task.id)
    assert len(history) == 1
    assert history[0].id == created_update.id
    assert history[0].author_id == file_db["user2_id"]
    assert history[0].completed_work == "Persistence verified"

    # 3. Update the task and verify change persists across reconnection
    update_task(
        created_task.id,
        title="Persisted Task v2",
        status="Done",
    )

    reconnect()
    updated_task = get_task(created_task.id)
    assert updated_task.title == "Persisted Task v2"
    assert updated_task.status == "Done"

    # 4. Save an approved handoff and verify it persists across reconnection
    saved_handoff = save_handoff(
        task_id=created_task.id,
        author_id=file_db["user1_id"],
        content="Approved handoff content.",
        source_update_ids=[created_update.id],
    )

    reconnect()
    handoffs = get_handoffs(created_task.id)
    assert len(handoffs) == 1
    assert handoffs[0].id == saved_handoff.id
    assert handoffs[0].status == "approved"
    assert handoffs[0].content == "Approved handoff content."
    assert handoffs[0].source_update_ids == [created_update.id]


def test_rollback_leaves_no_uncommitted_data_after_reconnection(file_db, monkeypatch):
    reconnect = file_db["reconnect"]

    # Baseline task committed first
    base_task = create_task(
        title="Baseline Task",
        sprint_id=file_db["sprint_id"],
        assignee_id=file_db["user1_id"],
        status="To Do",
    )

    # Test 1: direct session rollback discards uncommitted rows
    _, SessionCls = reconnect()
    with SessionCls() as db:
        db.add(
            Task(
                sprint_id=file_db["sprint_id"],
                title="Rolled Back Task",
                status="To Do",
            )
        )
        db.flush()
        db.rollback()

    reconnect()
    titles = [t.title for t in list_tasks(include_archived=True)]
    assert "Baseline Task" in titles
    assert "Rolled Back Task" not in titles

    # Test 2: service-level commit failure triggers rollback and leaves DB clean
    _, SessionCls = reconnect()

    class SimulatedCommitError(RuntimeError):
        pass

    def failing_session_factory():
        session = SessionCls()
        monkeypatch.setattr(
            session,
            "commit",
            lambda: (_ for _ in ()).throw(SimulatedCommitError("disk full")),
        )
        return session

    _patch_service_sessions(monkeypatch, failing_session_factory)

    with pytest.raises(SimulatedCommitError):
        create_task(
            title="Failed Commit Task",
            sprint_id=file_db["sprint_id"],
            assignee_id=file_db["user1_id"],
        )

    # Reconnect cleanly and verify nothing from the failed commit persisted
    reconnect()
    titles_after = [t.title for t in list_tasks(include_archived=True)]
    assert titles_after == ["Baseline Task"]
    assert get_task(base_task.id).title == "Baseline Task"


def test_handoff_rejects_cross_task_or_missing_source_updates_without_saving(test_db):
    other_task = create_task(
        title="Other Task",
        sprint_id=test_db["sprint_id"],
    )

    with pytest.raises(ValidationError):
        save_handoff(
            task_id=other_task.id,
            author_id=test_db["user_id"],
            content="Cross-task source update",
            source_update_ids=[test_db["update_id"]],
        )

    with pytest.raises(NotFoundError):
        save_handoff(
            task_id=test_db["task_id"],
            author_id=test_db["user_id"],
            content="Missing source update",
            source_update_ids=[999999],
        )

    assert get_handoffs(other_task.id) == []
    assert get_handoffs(test_db["task_id"]) == []
