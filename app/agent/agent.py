import os

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.tools import tool
from langchain_groq import ChatGroq

from app.agent.prompts import SYSTEM_PROMPT

from app.agent.tools import (
    tool_list_tasks,
    tool_get_task_history,
    tool_search_updates,
    tool_get_sprint_summary,
)


load_dotenv()


# ==========================================
# 1. Define LangChain Tools
# ==========================================

@tool("list_tasks")
def list_tasks_tool(
    status: str | None = None,
    assignee_id: int | None = None,
    include_archived: bool = False,
) -> dict:
    """Retrieve project tasks with optional status and assignee filters."""
    return tool_list_tasks(
        status=status,
        assignee_id=assignee_id,
        include_archived=include_archived,
    )


@tool("get_task_history")
def get_task_history_tool(task_id: int) -> dict:
    """Retrieve all progress updates for a specific task."""
    return tool_get_task_history(task_id)


@tool("search_updates")
def search_updates_tool(query: str, limit: int = 10) -> dict:
    """Search stored project updates using keywords. Maximum limit is 25."""
    return tool_search_updates(query=query, limit=limit)


@tool("get_sprint_summary")
def get_sprint_summary_tool() -> dict:
    """Retrieve the current active sprint summary and blocked tasks."""
    return tool_get_sprint_summary()


# ==========================================
# 2. Create the LLM
# ==========================================

def create_project_agent():
    """Initialize the Groq model and create the project agent."""

    api_key = os.getenv("GROQ_API_KEY")
    model_name = os.getenv("GROQ_MODEL")

    if not api_key:
        raise ValueError("GROQ_API_KEY is missing from environment variables.")

    if not model_name:
        raise ValueError("GROQ_MODEL is missing from environment variables.")

    llm = ChatGroq(
        model=model_name,
        api_key=api_key,
        temperature=0,
    )

    # ==========================================
    # 3. Create the Agent
    # ==========================================

    agent = create_agent(
        model=llm,
        tools=[
            list_tasks_tool,
            get_task_history_tool,
            search_updates_tool,
            get_sprint_summary_tool,
        ],
        system_prompt=SYSTEM_PROMPT,
    )

    return agent


# ==========================================
# 4. Ask the Agent
# ==========================================

def ask_agent(question: str) -> str:
    """Send a question to the agent and return its final answer."""

    if not isinstance(question, str) or not question.strip():
        raise ValueError("Question cannot be empty.")

    agent = create_project_agent()

    result = agent.invoke({
        "messages": [
            {"role": "user", "content": question.strip()}
        ]
    })

    # Get the final AI response
    for message in reversed(result["messages"]):
        if message.type == "ai" and message.content:
            return message.content

    return "The agent could not generate an answer."