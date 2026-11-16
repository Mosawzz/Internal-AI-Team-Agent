
import pytest

from datetime import date

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base, User, Project, Sprint, Task, Update


@pytest.fixture
def test_db(monkeypatch):

    # Create an isolated in-memory SQLite database
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Enable foreign keys
    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)

    TestSessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )

    # Replace the real database session in all services
    from app.services import (
        tasks_service,
        updates_service,
        sprint_service,
        users_service,
        handoff_service,
    )

    for module in [
        tasks_service,
        updates_service,
        sprint_service,
        users_service,
        handoff_service,
    ]:
        monkeypatch.setattr(
            module,
            "SessionLocal",
            TestSessionLocal
        )

    # Create test data
    with TestSessionLocal() as db:

        user = User(
            display_name="Test User",
            role="project_manager",
        )

        project = Project(
            name="Test Project",
            goal="Testing project services",
        )

        db.add_all([user, project])
        db.flush()

        sprint = Sprint(
            project_id=project.id,
            goal="Testing sprint",
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 30),
            status="active",
        )

        db.add(sprint)
        db.flush()

        task = Task(
            sprint_id=sprint.id,
            title="Test Task",
            description="Task for testing",
            assignee_id=user.id,
            status="In Progress",
        )

        done_task = Task(
            sprint_id=sprint.id,
            title="Completed Task",
            assignee_id=user.id,
            status="Done",
        )

        db.add_all([task, done_task])
        db.flush()

        update = Update(
            task_id=task.id,
            author_id=user.id,
            entry_type="progress",
            raw_text="Initial test update",
            completed_work="Initial implementation",
        )

        done_update = Update(
            task_id=done_task.id,
            author_id=user.id,
            entry_type="progress",
            raw_text="Completed task update",
            completed_work="Task completed",
        )

        db.add_all([update, done_update])
        db.commit()

        test_data = {
            "user_id": user.id,
            "sprint_id": sprint.id,
            "task_id": task.id,
            "done_task_id": done_task.id,
            "update_id": update.id,
            "done_update_id": done_update.id,
        }

    yield test_data

    engine.dispose()
