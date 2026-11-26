
import os
import tempfile

import pytest
from sqlalchemy import create_engine, event, inspect as sa_inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base, User, Project, Sprint, Task, Update, Handoff


EXPECTED_TABLES = {"users", "projects", "sprints", "tasks", "updates", "handoffs"}


@pytest.fixture
def temp_db(monkeypatch):
    """Provide an isolated file-backed SQLite database for setup tests."""

    fd, tmp_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(tmp_path)  # start truly empty

    db_url = f"sqlite:///{tmp_path}"

    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def fk_on(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    TempSession = sessionmaker(
        bind=engine, autoflush=False, autocommit=False
    )

    # Patch the production database module
    import app.db.database as db_mod
    monkeypatch.setattr(db_mod, "engine", engine)
    monkeypatch.setattr(db_mod, "SessionLocal", TempSession)

    # Also patch every module that imports SessionLocal directly
    from app.services import (
        tasks_service,
        updates_service,
        sprint_service,
        users_service,
        handoff_service,
    )
    import app.db.seed as seed_mod

    for module in [
        tasks_service,
        updates_service,
        sprint_service,
        users_service,
        handoff_service,
        seed_mod,
    ]:
        monkeypatch.setattr(module, "SessionLocal", TempSession)

    yield {
        "path": tmp_path,
        "engine": engine,
        "SessionLocal": TempSession,
    }

    engine.dispose()

    try:
        os.unlink(tmp_path)
    except OSError:
        pass


# -------------------------
# Initialization tests
# -------------------------

def test_init_creates_all_tables(temp_db):
    """init_db must create all six model tables."""
    from app.db.database import init_db

    init_db()

    tables = set(sa_inspect(temp_db["engine"]).get_table_names())
    missing = EXPECTED_TABLES - tables

    assert not missing, f"Missing tables: {missing}"


def test_init_is_idempotent(temp_db):
    """Running init_db twice must not raise or drop tables."""
    from app.db.database import init_db

    init_db()
    init_db()

    tables = set(sa_inspect(temp_db["engine"]).get_table_names())

    assert EXPECTED_TABLES.issubset(tables)


# -------------------------
# Seed tests
# -------------------------

def test_seed_creates_expected_records(temp_db):
    """seed_data must create the expected number of records."""
    from app.db.seed import seed_data

    seed_data()

    db = temp_db["SessionLocal"]()

    assert db.query(User).count() == 5
    assert db.query(Project).count() == 1
    assert db.query(Sprint).count() == 1
    assert db.query(Task).count() == 10
    assert db.query(Update).count() == 5

    db.close()


def test_seed_is_idempotent(temp_db):
    """Running seed_data three times must not duplicate records."""
    from app.db.seed import seed_data

    seed_data()
    seed_data()
    seed_data()

    db = temp_db["SessionLocal"]()

    assert db.query(User).count() == 5
    assert db.query(Project).count() == 1
    assert db.query(Task).count() == 10
    assert db.query(Update).count() == 5

    db.close()


def test_seed_initializes_tables_first(temp_db):
    """seed_data on an empty database must work without a prior init_db call."""
    from app.db.seed import seed_data

    # Tables do not exist yet — seed_data should handle it
    seed_data()

    tables = set(sa_inspect(temp_db["engine"]).get_table_names())

    assert EXPECTED_TABLES.issubset(tables)

    db = temp_db["SessionLocal"]()

    assert db.query(Project).count() == 1

    db.close()


# -------------------------
# Relationship tests
# -------------------------

def test_seed_relationships_are_valid(temp_db):
    """Every seeded FK reference must point to an existing record."""
    from app.db.seed import seed_data

    seed_data()

    db = temp_db["SessionLocal"]()

    for task in db.query(Task).all():
        assert db.get(Sprint, task.sprint_id) is not None
        assert db.get(User, task.assignee_id) is not None

    for update in db.query(Update).all():
        assert db.get(User, update.author_id) is not None
        if update.task_id is not None:
            assert db.get(Task, update.task_id) is not None

    sprint = db.query(Sprint).first()
    assert db.get(Project, sprint.project_id) is not None

    db.close()


# -------------------------
# FK enforcement test
# -------------------------

def test_fk_constraints_enforced(temp_db):
    """SQLite must reject inserts that violate FK constraints."""
    from app.db.database import init_db

    init_db()

    db = temp_db["SessionLocal"]()

    task = Task(sprint_id=99999, title="Orphan", status="To Do")
    db.add(task)

    with pytest.raises(Exception, match="(?i)foreign key"):
        db.commit()

    db.rollback()
    db.close()
