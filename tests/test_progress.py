
import pytest
from unittest.mock import MagicMock

from langchain_core.exceptions import OutputParserException

from app.ai.progress import (
    ProgressUpdateDraft,
    extract_progress_draft,
)

from app.errors import (
    ExtractionError,
    ModelUnavailableError,
)


@pytest.fixture
def mock_groq(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-api-key")
    monkeypatch.setenv("GROQ_MODEL", "test-model")

    mock_llm = MagicMock()
    mock_structured_llm = MagicMock()

    mock_llm.with_structured_output.return_value = mock_structured_llm

    monkeypatch.setattr(
        "app.ai.progress.ChatGroq",
        lambda **kwargs: mock_llm
    )

    return mock_structured_llm


def test_extract_progress_success(mock_groq):
    expected_draft = ProgressUpdateDraft(
        completed_work=["Implemented progress schema"],
        remaining_work=["Write unit tests"],
        blockers=[],
        next_step="Test extraction module"
    )

    mock_groq.invoke.return_value = expected_draft

    result = extract_progress_draft(
        1,
        "I implemented the progress schema. "
        "I still need to write unit tests."
    )

    assert result == expected_draft
    assert mock_groq.invoke.call_count == 1


def test_extract_progress_missing_fields(mock_groq):
    mock_groq.invoke.return_value = {
        "completed_work": ["Created the schema"]
    }

    result = extract_progress_draft(
        1,
        "I created the schema."
    )

    assert result.completed_work == ["Created the schema"]
    assert result.remaining_work == []
    assert result.blockers == []
    assert result.next_step is None


def test_extract_progress_retry_success(mock_groq):
    expected_draft = ProgressUpdateDraft(
        completed_work=["Implemented extraction"],
        remaining_work=[],
        blockers=[],
        next_step=None
    )

    mock_groq.invoke.side_effect = [
        OutputParserException("Invalid output", llm_output="bad"),
        expected_draft
    ]

    result = extract_progress_draft(
        1,
        "I implemented extraction."
    )

    assert result == expected_draft
    assert mock_groq.invoke.call_count == 2


def test_extract_progress_invalid_output(mock_groq):
    mock_groq.invoke.side_effect = [
        OutputParserException("Invalid output", llm_output="bad"),
        OutputParserException("Invalid output again", llm_output="bad")
    ]

    with pytest.raises(ExtractionError):
        extract_progress_draft(1, "I worked on the task.")

    assert mock_groq.invoke.call_count == 2


def test_extract_progress_model_unavailable(mock_groq):
    mock_groq.invoke.side_effect = Exception("Connection failed")

    with pytest.raises(ModelUnavailableError):
        extract_progress_draft(1, "I completed the task.")

    assert mock_groq.invoke.call_count == 1
