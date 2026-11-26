from datetime import datetime
from unittest.mock import MagicMock

import pytest
from langchain_core.exceptions import OutputParserException
from streamlit.testing.v1 import AppTest

from app.ai.progress import ProgressUpdateDraft, extract_progress_draft
from app.errors import ExtractionError, ModelUnavailableError, ValidationError
from app.services.updates_service import add_update, get_task_history


@pytest.fixture
def mock_groq(monkeypatch):
    """Mock ChatGroq structured LLM calls cleanly."""
    monkeypatch.setenv("GROQ_API_KEY", "test-api-key")
    monkeypatch.setenv("GROQ_MODEL", "test-model")

    mock_llm = MagicMock()
    mock_structured_llm = MagicMock()
    mock_llm.with_structured_output.return_value = mock_structured_llm

    monkeypatch.setattr("app.ai.progress.ChatGroq", lambda **kwargs: mock_llm)
    return mock_structured_llm


def _run_tasks_updates_app():
    """Entrypoint wrapper for Streamlit AppTest."""
    from app.ui.tasks_updates import render_tasks_updates

    render_tasks_updates()


# =========================================================
# 1. Extraction Schema, Validation & Failure Isolation
# =========================================================


def test_extract_progress_ignores_unknown_fields_and_keeps_missing_empty(mock_groq):
    mock_groq.invoke.return_value = {
        "completed_work": ["Built API endpoint"],
        "invented_extra_field": "should be ignored",
    }

    draft = extract_progress_draft(1, "I built the API endpoint.")

    assert draft.completed_work == ["Built API endpoint"]
    assert draft.remaining_work == []
    assert draft.blockers == []
    assert draft.next_step is None
    assert not hasattr(draft, "invented_extra_field")


@pytest.mark.parametrize(
    "bad_output",
    [
        {"completed_work": "should-be-a-list"},
        {"completed_work": [123]},
        {"next_step": 456},
        None,
        "plain unparsed string",
    ],
)
def test_extract_progress_rejects_malformed_or_invalid_type_output(mock_groq, bad_output):
    mock_groq.invoke.return_value = bad_output

    with pytest.raises(ExtractionError):
        extract_progress_draft(1, "Worked on tests.")


def test_extract_progress_rejects_invalid_inputs_without_calling_model(mock_groq):
    for bad_task_id in [0, -1, "1", None, True]:
        with pytest.raises(ExtractionError):
            extract_progress_draft(bad_task_id, "Valid text")

    for bad_text in ["", "   ", None, 999]:
        with pytest.raises(ExtractionError):
            extract_progress_draft(1, bad_text)

    assert mock_groq.invoke.call_count == 0


def test_extract_progress_missing_config_and_init_failure(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    monkeypatch.setattr("app.ai.progress.load_dotenv", lambda: None)

    with pytest.raises(ModelUnavailableError):
        extract_progress_draft(1, "Finished setup.")

    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("GROQ_MODEL", "test-model")
    monkeypatch.setattr(
        "app.ai.progress.ChatGroq",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("client init error")),
    )

    with pytest.raises(ModelUnavailableError):
        extract_progress_draft(1, "Finished setup.")


def test_extract_progress_does_not_write_to_database(test_db, mock_groq):
    task_id = test_db["task_id"]
    before_history = get_task_history(task_id)

    mock_groq.invoke.return_value = ProgressUpdateDraft(
        completed_work=["Drafted feature"],
        remaining_work=["Review draft"],
        blockers=[],
        next_step="Await user confirmation",
    )

    draft = extract_progress_draft(task_id, "I drafted the feature.")
    assert draft.completed_work == ["Drafted feature"]

    after_history = get_task_history(task_id)
    assert [u.id for u in after_history] == [u.id for u in before_history]


# =========================================================
# 2. UI Review -> Approval -> Persistence Boundary (AppTest)
# =========================================================


def _select_task_in_app(at: AppTest, task_id: int) -> None:
    """Select the target task in the Tasks & Updates Streamlit view."""
    for sb in at.selectbox:
        if sb.label == "Select a task":
            matching = [opt for opt in sb.options if opt.startswith(f"T-{task_id} —")]
            assert matching, f"Task T-{task_id} not found in options: {sb.options}"
            sb.select(matching[0]).run()
            return
    raise AssertionError("Select a task selectbox not found")


def test_ui_extract_does_not_persist_before_explicit_confirmation(test_db, monkeypatch):
    task_id = test_db["task_id"]
    before_count = len(get_task_history(task_id))

    draft = ProgressUpdateDraft(
        completed_work=["Implemented schema"],
        remaining_work=["Write regression tests"],
        blockers=["Waiting on spec"],
        next_step="Run pytest",
    )
    monkeypatch.setattr(
        "app.ui.tasks_updates.extract_progress_draft",
        lambda task_id, free_text: draft,
    )

    at = AppTest.from_function(_run_tasks_updates_app, default_timeout=15).run()
    _select_task_in_app(at, task_id)

    # Enter free text and click "Extract Progress with AI"
    text_area = next(ta for ta in at.text_area if ta.key == "ai_progress_text")
    text_area.input("Implemented schema, waiting on spec.").run()

    extract_btn = next(b for b in at.button if b.label == "Extract Progress with AI")
    extract_btn.click().run()

    # Draft review widgets must appear populated
    assert any(ta.key == "review_completed" and "Implemented schema" in ta.value for ta in at.text_area)
    # Still NO new database record before explicit confirmation
    assert len(get_task_history(task_id)) == before_count

    # Editing review fields without clicking "Confirm and Save Progress" must NOT persist
    review_completed = next(ta for ta in at.text_area if ta.key == "review_completed")
    review_completed.input("Edited but unconfirmed").run()
    assert len(get_task_history(task_id)) == before_count


def test_ui_confirm_saves_edited_values_with_references_and_timestamp(test_db, monkeypatch):
    task_id = test_db["task_id"]
    author_id = test_db["user_id"]
    before_ids = {u.id for u in get_task_history(task_id)}

    original_draft = ProgressUpdateDraft(
        completed_work=["Original draft completed"],
        remaining_work=["Original draft remaining"],
        blockers=["Original blocker"],
        next_step="Original next step",
    )
    monkeypatch.setattr(
        "app.ui.tasks_updates.extract_progress_draft",
        lambda task_id, free_text: original_draft,
    )

    at = AppTest.from_function(_run_tasks_updates_app, default_timeout=15).run()
    _select_task_in_app(at, task_id)

    next(ta for ta in at.text_area if ta.key == "ai_progress_text").input(
        "Raw progress text from user."
    ).run()
    next(b for b in at.button if b.label == "Extract Progress with AI").click().run()

    # User edits all review fields before confirming
    next(ta for ta in at.text_area if ta.key == "review_completed").input(
        "Approved item 1\nApproved item 2"
    )
    next(ta for ta in at.text_area if ta.key == "review_remaining").input(
        "Approved remaining item"
    )
    next(ta for ta in at.text_area if ta.key == "review_blockers").input("")
    next(ta for ta in at.text_area if ta.key == "review_next_step").input(
        "Approved final next step"
    )

    confirm_btn = next(b for b in at.button if b.label == "Confirm and Save Progress")
    confirm_btn.click().run()

    # Should succeed without UI errors
    assert not at.error, f"Unexpected UI error(s): {[e.value for e in at.error]}"

    after_history = get_task_history(task_id)
    new_updates = [u for u in after_history if u.id not in before_ids]
    assert len(new_updates) == 1

    saved = new_updates[0]
    assert saved.task_id == task_id
    assert saved.author_id == author_id
    assert saved.entry_type == "progress"
    assert saved.raw_text == "Raw progress text from user."
    assert saved.completed_work == "Approved item 1\nApproved item 2"
    assert saved.remaining_work == "Approved remaining item"
    assert saved.blockers is None
    assert saved.next_step == "Approved final next step"
    # Verify ISO-8601 UTC timestamp format
    datetime.strptime(saved.created_at, "%Y-%m-%dT%H:%M:%SZ")


def test_ui_reextraction_refreshes_review_fields_without_stale_values(test_db, monkeypatch):
    task_id = test_db["task_id"]

    drafts = iter(
        [
            ProgressUpdateDraft(
                completed_work=["First draft work"],
                remaining_work=["First remaining"],
                blockers=[],
                next_step="First next",
            ),
            ProgressUpdateDraft(
                completed_work=["Second draft work"],
                remaining_work=["Second remaining"],
                blockers=["Second blocker"],
                next_step="Second next",
            ),
        ]
    )
    monkeypatch.setattr(
        "app.ui.tasks_updates.extract_progress_draft",
        lambda task_id, free_text: next(drafts),
    )

    at = AppTest.from_function(_run_tasks_updates_app, default_timeout=15).run()
    _select_task_in_app(at, task_id)

    # First extraction
    next(ta for ta in at.text_area if ta.key == "ai_progress_text").input("First update").run()
    next(b for b in at.button if b.label == "Extract Progress with AI").click().run()
    assert next(ta for ta in at.text_area if ta.key == "review_completed").value == "First draft work"

    # Second extraction without saving first — review fields must refresh!
    next(ta for ta in at.text_area if ta.key == "ai_progress_text").input("Second update").run()
    next(b for b in at.button if b.label == "Extract Progress with AI").click().run()
    assert next(ta for ta in at.text_area if ta.key == "review_completed").value == "Second draft work"
    assert next(ta for ta in at.text_area if ta.key == "review_remaining").value == "Second remaining"
    assert next(ta for ta in at.text_area if ta.key == "review_blockers").value == "Second blocker"
    assert next(ta for ta in at.text_area if ta.key == "review_next_step").value == "Second next"


def test_ui_extraction_and_save_errors_do_not_corrupt_records(test_db, monkeypatch):
    task_id = test_db["task_id"]
    before_history = get_task_history(task_id)

    # Extraction failure shows clear error and saves nothing
    monkeypatch.setattr(
        "app.ui.tasks_updates.extract_progress_draft",
        lambda task_id, free_text: (_ for _ in ()).throw(
            ModelUnavailableError("Groq service unavailable")
        ),
    )
    at = AppTest.from_function(_run_tasks_updates_app, default_timeout=15).run()
    _select_task_in_app(at, task_id)
    next(ta for ta in at.text_area if ta.key == "ai_progress_text").input("Attempt 1").run()
    next(b for b in at.button if b.label == "Extract Progress with AI").click().run()

    assert any("Groq service unavailable" in e.value for e in at.error)
    assert len(get_task_history(task_id)) == len(before_history)

    # Validation error during save keeps existing records intact
    with pytest.raises(ValidationError, match="string or None"):
        add_update(
            author_id=test_db["user_id"],
            task_id=task_id,
            entry_type="progress",
            completed_work=["invalid-list"],
        )

    after_history = get_task_history(task_id)
    assert [(u.id, u.completed_work) for u in after_history] == [
        (u.id, u.completed_work) for u in before_history
    ]
