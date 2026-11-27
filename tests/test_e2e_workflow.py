import os
import tempfile
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from streamlit.testing.v1 import AppTest

import app.db.database as db_mod
import app.db.seed as seed_mod
from app.agent import agent as agent_module
from app.ai.progress import ProgressUpdateDraft
from app.services import (
    handoff_service,
    sprint_service,
    tasks_service,
    updates_service,
    users_service,
)
from app.services.handoff_service import get_handoffs
from app.services.tasks_service import list_tasks
from app.services.updates_service import get_task_history


SESSION_MODULES = [
    db_mod,
    seed_mod,
    tasks_service,
    updates_service,
    sprint_service,
    users_service,
    handoff_service,
]


@pytest.fixture
def clean_file_app_db(monkeypatch):
    """Provide a brand-new, empty file-backed SQLite DB with reconnect support."""
    fd, tmp_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(tmp_path)

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
        monkeypatch.setattr(db_mod, "engine", engine)
        for mod in SESSION_MODULES:
            monkeypatch.setattr(mod, "SessionLocal", session_factory)
        return engine, session_factory

    connect()
    yield {"db_path": tmp_path, "reconnect": connect}

    while engines:
        engines.pop().dispose()
    try:
        os.unlink(tmp_path)
    except OSError:
        pass


def _select_task_by_title(at: AppTest, title_substring: str) -> int:
    for sb in at.selectbox:
        if sb.label == "Select a task":
            matching = [opt for opt in sb.options if title_substring in opt]
            assert matching, f"Task '{title_substring}' not found in {sb.options}"
            sb.select(matching[0]).run()
            return int(matching[0].split(" — ", 1)[0].removeprefix("T-"))
    raise AssertionError("Select a task selectbox not found")


def test_app_smoke_main_overview_and_tasks_screens(clean_file_app_db):
    """Smoke test README clean setup + launching app/main.py across both screens."""
    seed_mod.seed_data()

    at = AppTest.from_file("app/main.py", default_timeout=15).run()
    assert not at.error, f"Overview screen errors: {[e.value for e in at.error]}"
    assert any("Internal Team Agent" in t.value for t in at.title)
    assert any("Build the MVP database" in m.value for m in at.markdown)

    # Switch to Tasks & Updates via sidebar navigation
    nav = next(r for r in at.sidebar.radio if r.label == "Go to")
    nav.set_value("Tasks & Updates").run()
    assert not at.error, f"Tasks & Updates screen errors: {[e.value for e in at.error]}"
    assert any("Tasks & Updates" in t.value for t in at.title)


def test_end_to_end_user_journey_across_modules_and_restart(
    clean_file_app_db, monkeypatch
):
    """Exercise clean setup -> UI task creation -> AI progress -> Q&A -> handoff -> restart."""
    reconnect = clean_file_app_db["reconnect"]

    # 1. Clean seeded database
    seed_mod.seed_data()

    # Mock Groq LLM for deterministic progress extraction
    monkeypatch.setenv("GROQ_API_KEY", "test-api-key")
    monkeypatch.setenv("GROQ_MODEL", "test-model")
    mock_llm = MagicMock()
    mock_structured = MagicMock()
    mock_structured.invoke.return_value = ProgressUpdateDraft(
        completed_work=["Configured end-to-end smoke check"],
        remaining_work=["Finish Stage 5 regression"],
        blockers=[],
        next_step="Generate task handoff",
    )
    mock_llm.with_structured_output.return_value = mock_structured
    monkeypatch.setattr("app.ai.progress.ChatGroq", lambda **kwargs: mock_llm)

    # 2. Launch app and navigate to Tasks & Updates
    at = AppTest.from_file("app/main.py", default_timeout=15).run()
    next(r for r in at.sidebar.radio if r.label == "Go to").set_value(
        "Tasks & Updates"
    ).run()
    assert not at.error

    # 3. Create a new task through the UI form
    next(ti for ti in at.text_input if ti.label == "Task Title").input(
        "E2E Workflow Task"
    )
    next(ta for ta in at.text_area if ta.label == "Task Description").input(
        "Verify full cross-module workflow."
    )
    next(sb for sb in at.selectbox if sb.label == "Initial Status").select(
        "In Progress"
    )
    next(b for b in at.button if b.label == "Create Task").click().run()
    assert not at.error

    created_tasks = [t for t in list_tasks() if t.title == "E2E Workflow Task"]
    assert len(created_tasks) == 1
    task_id = created_tasks[0].id

    # 4. Select created task and extract structured progress (must NOT save yet)
    selected_id = _select_task_by_title(at, "E2E Workflow Task")
    assert selected_id == task_id

    next(ta for ta in at.text_area if ta.key == "ai_progress_text").input(
        "Configured end-to-end smoke check; Stage 5 regression remains."
    ).run()
    next(b for b in at.button if b.label == "Extract Progress with AI").click().run()
    assert not at.error
    assert get_task_history(task_id) == []

    # 5. Review/edit and explicitly confirm progress update
    next(ta for ta in at.text_area if ta.key == "review_completed").input(
        "Configured end-to-end smoke check\nVerified clean DB seed"
    )
    next(b for b in at.button if b.label == "Confirm and Save Progress").click().run()
    assert not at.error

    # 6. Verify DB persistence and task history retrieval
    history = get_task_history(task_id)
    assert len(history) == 1
    update_id = history[0].id
    assert history[0].completed_work == (
        "Configured end-to-end smoke check\nVerified clean DB seed"
    )

    # 7. Ask answerable & unanswerable questions via read-only agent tools
    class E2EFakeAgent:
        def invoke(self, inputs):
            q = inputs["messages"][0]["content"]
            if "E2E Workflow Task" in q or "smoke check" in q:
                hist = agent_module.get_task_history_tool.invoke({"task_id": task_id})
                search = agent_module.search_updates_tool.invoke(
                    {"query": "smoke check"}
                )
                rec = search["records"][0]
                return {
                    "messages": [
                        SimpleNamespace(
                            type="ai",
                            content=(
                                f"Task T-{task_id} has update {rec['source_id']} "
                                f"(total history={hist['count']}): {rec['text']}"
                            ),
                        )
                    ]
                }

            empty_search = agent_module.search_updates_tool.invoke(
                {"query": "QuantumDeploymentBudget999"}
            )
            assert empty_search["count"] == 0
            return {
                "messages": [
                    SimpleNamespace(
                        type="ai",
                        content="Insufficient evidence in stored project records.",
                    )
                ]
            }

    monkeypatch.setattr(agent_module, "create_project_agent", lambda: E2EFakeAgent())

    answerable = agent_module.ask_agent("What did we complete on E2E Workflow Task?")
    assert f"T-{task_id}" in answerable
    assert f"U-{update_id}" in answerable
    assert "Configured end-to-end smoke check" in answerable

    unanswerable = agent_module.ask_agent("What is QuantumDeploymentBudget999?")
    assert "insufficient evidence" in unanswerable.lower()

    # 8. Generate handoff draft in UI (must NOT save before approval)
    next(b for b in at.button if b.label == "Generate Handoff Draft").click().run()
    assert not at.error
    assert get_handoffs(task_id) == []

    handoff_box = next(ta for ta in at.text_area if ta.key == f"handoff_content_{task_id}")
    assert f"T-{task_id}" in handoff_box.value
    assert f"U-{update_id}" in handoff_box.value
    assert "Verified clean DB seed" in handoff_box.value

    # 9. Review/edit and approve handoff
    edited_handoff = handoff_box.value + "\nE2E Reviewer Sign-off: Approved."
    next(ta for ta in at.text_area if ta.key == f"handoff_content_{task_id}").input(
        edited_handoff
    )
    next(b for b in at.button if b.label == "Approve and Save Handoff").click().run()
    assert not at.error

    # 10. Dispose engine, reconnect cleanly, and restart UI to prove persistence
    reconnect()

    restarted_at = AppTest.from_file("app/main.py", default_timeout=15).run()
    assert not restarted_at.error
    next(r for r in restarted_at.sidebar.radio if r.label == "Go to").set_value(
        "Tasks & Updates"
    ).run()
    assert not restarted_at.error

    reloaded_id = _select_task_by_title(restarted_at, "E2E Workflow Task")
    assert reloaded_id == task_id

    persisted_history = get_task_history(task_id)
    assert len(persisted_history) == 1
    assert persisted_history[0].id == update_id

    persisted_handoffs = get_handoffs(task_id)
    assert len(persisted_handoffs) == 1
    assert persisted_handoffs[0].status == "approved"
    assert persisted_handoffs[0].source_update_ids == [update_id]
    assert "E2E Reviewer Sign-off: Approved." in persisted_handoffs[0].content
