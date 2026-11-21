from types import SimpleNamespace
import pytest
from app.agent import agent as agent_module
from unittest.mock import Mock

class FakeAgent:
    """A lightweight fake agent used to test ask_agent without Groq."""

    def __init__(self, messages):
        self.messages = messages
        self.received_input = None

    def invoke(self, inputs):
        self.received_input = inputs
        return {"messages": self.messages}


def test_ask_agent_returns_final_ai_answer(monkeypatch):
    """The function should return the last non-empty AI message."""

    fake_agent = FakeAgent([
        SimpleNamespace(type="human", content="Hello"),
        SimpleNamespace(type="ai", content="First response"),
        SimpleNamespace(type="tool", content="Tool result"),
        SimpleNamespace(type="ai", content="Final answer"),
    ])

    monkeypatch.setattr(
        agent_module,
        "create_project_agent",
        lambda: fake_agent,
    )

    result = agent_module.ask_agent("  What is the sprint goal?  ")

    assert result == "Final answer"
    assert fake_agent.received_input == {
        "messages": [
            {"role": "user", "content": "What is the sprint goal?"}
        ]
    }


@pytest.mark.parametrize("question", ["", "   ", None, 123])
def test_ask_agent_rejects_invalid_question(monkeypatch, question):
    """Empty or non-string questions should raise ValueError."""

    def unexpected_agent_creation():
        pytest.fail("Agent should not be created for an invalid question.")

    monkeypatch.setattr(
        agent_module,
        "create_project_agent",
        unexpected_agent_creation,
    )

    with pytest.raises(ValueError, match="Question cannot be empty"):
        agent_module.ask_agent(question)


def test_ask_agent_returns_fallback_when_no_ai_answer(monkeypatch):
    """The function should return a fallback if no AI answer exists."""

    fake_agent = FakeAgent([
        SimpleNamespace(type="human", content="Hello"),
        SimpleNamespace(type="tool", content="Tool result"),
        SimpleNamespace(type="ai", content=""),
    ])

    monkeypatch.setattr(
        agent_module,
        "create_project_agent",
        lambda: fake_agent,
    )

    result = agent_module.ask_agent("Hello")

    assert result == "The agent could not generate an answer."



def test_create_project_agent_requires_api_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_MODEL", "test-model")

    with pytest.raises(ValueError, match="GROQ_API_KEY is missing"):
        agent_module.create_project_agent()


def test_create_project_agent_requires_model(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "fake-api-key")
    monkeypatch.delenv("GROQ_MODEL", raising=False)

    with pytest.raises(ValueError, match="GROQ_MODEL is missing"):
        agent_module.create_project_agent()


def test_create_project_agent_requires_api_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_MODEL", "test-model")

    with pytest.raises(ValueError, match="GROQ_API_KEY is missing"):
        agent_module.create_project_agent()


def test_create_project_agent_requires_model(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "fake-api-key")
    monkeypatch.delenv("GROQ_MODEL", raising=False)

    with pytest.raises(ValueError, match="GROQ_MODEL is missing"):
        agent_module.create_project_agent()


def test_create_project_agent_success(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "fake-api-key")
    monkeypatch.setenv("GROQ_MODEL", "test-model")

    fake_llm = Mock()
    fake_agent = Mock()

    chatgroq_mock = Mock(return_value=fake_llm)
    create_agent_mock = Mock(return_value=fake_agent)

    monkeypatch.setattr(agent_module, "ChatGroq", chatgroq_mock)
    monkeypatch.setattr(agent_module, "create_agent", create_agent_mock)

    result = agent_module.create_project_agent()

    assert result is fake_agent

    chatgroq_mock.assert_called_once_with(
        model="test-model",
        api_key="fake-api-key",
        temperature=0
    )

    create_agent_mock.assert_called_once()

    kwargs = create_agent_mock.call_args.kwargs

    assert kwargs["model"] is fake_llm
    assert len(kwargs["tools"]) == 4
    assert kwargs["system_prompt"] == agent_module.SYSTEM_PROMPT
