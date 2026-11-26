from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.agent import agent as agent_module
from app.agent import tools as tools_module
from app.services.handoff_service import get_handoffs, save_handoff
from app.services.tasks_service import create_task, list_tasks
from app.services.updates_service import add_update, get_task_history


STANDARD_RESULT_KEYS = {"ok", "tool", "count", "records", "error"}


def _snapshot_db(task_ids: list[int]) -> dict:
    """Capture counts and identifiers across tasks, updates, and handoffs."""
    tasks = list_tasks(include_archived=True)
    histories = {tid: [u.id for u in get_task_history(tid)] for tid in task_ids}
    handoffs = {tid: [h.id for h in get_handoffs(tid)] for tid in task_ids}
    return {
        "tasks": [(t.id, t.title, t.status, t.archived) for t in tasks],
        "histories": histories,
        "handoffs": handoffs,
    }


# =========================================================
# 1. Argument Validation & Standard Result Contracts
# =========================================================


@pytest.mark.parametrize(
    "bad_status",
    ["", "Pending", "Completed", 123],
)
def test_tool_list_tasks_rejects_invalid_status(test_db, bad_status):
    result = tools_module.tool_list_tasks(status=bad_status)
    assert set(result.keys()) == STANDARD_RESULT_KEYS
    assert result["ok"] is False
    assert result["tool"] == "list_tasks"
    assert result["count"] == 0
    assert result["records"] == []
    assert result["error"]


@pytest.mark.parametrize(
    "bad_kwargs",
    [
        {"assignee_id": 0},
        {"assignee_id": -3},
        {"assignee_id": True},
        {"assignee_id": "1"},
        {"include_archived": "yes"},
        {"include_archived": 1},
    ],
)
def test_tool_list_tasks_rejects_invalid_filters(test_db, bad_kwargs):
    result = tools_module.tool_list_tasks(**bad_kwargs)
    assert set(result.keys()) == STANDARD_RESULT_KEYS
    assert result["ok"] is False
    assert result["count"] == 0
    assert result["records"] == []
    assert result["error"]


def test_tool_list_tasks_valid_filters_and_archived_flag(test_db):
    from app.services.tasks_service import archive_task

    archive_task(test_db["done_task_id"])

    active_only = tools_module.tool_list_tasks(status="In Progress")
    assert active_only["ok"] is True
    assert active_only["count"] == 1
    assert active_only["records"][0]["source_id"] == f"T-{test_db['task_id']}"

    done_excluded = tools_module.tool_list_tasks(status="Done", include_archived=False)
    assert done_excluded["ok"] is True
    assert done_excluded["count"] == 0

    done_included = tools_module.tool_list_tasks(status="Done", include_archived=True)
    assert done_included["ok"] is True
    assert done_included["count"] == 1
    assert done_included["records"][0]["source_id"] == f"T-{test_db['done_task_id']}"


@pytest.mark.parametrize("bad_task_id", [0, -1, True, False, "1", None])
def test_tool_get_task_history_rejects_invalid_ids(test_db, bad_task_id):
    result = tools_module.tool_get_task_history(bad_task_id)
    assert set(result.keys()) == STANDARD_RESULT_KEYS
    assert result["ok"] is False
    assert result["tool"] == "get_task_history"
    assert result["count"] == 0
    assert result["records"] == []
    assert result["error"]


@pytest.mark.parametrize("bad_query", ["", "   ", "\n\t", None, 123])
def test_tool_search_updates_rejects_empty_or_non_string_query(test_db, bad_query):
    result = tools_module.tool_search_updates(query=bad_query)
    assert set(result.keys()) == STANDARD_RESULT_KEYS
    assert result["ok"] is False
    assert result["tool"] == "search_updates"
    assert result["count"] == 0
    assert result["records"] == []
    assert result["error"]


@pytest.mark.parametrize(
    "bad_limit",
    [0, -1, -25, 26, 100, "10", 5.5, None, True, False],
)
def test_tool_search_updates_rejects_invalid_limits(test_db, bad_limit):
    result = tools_module.tool_search_updates(query="Initial", limit=bad_limit)
    assert set(result.keys()) == STANDARD_RESULT_KEYS
    assert result["ok"] is False
    assert result["tool"] == "search_updates"
    assert result["count"] == 0
    assert result["records"] == []
    assert result["error"]


def test_tool_search_updates_accepts_boundary_limits(test_db):
    for i in range(28):
        add_update(
            author_id=test_db["user_id"],
            task_id=test_db["task_id"],
            entry_type="note",
            raw_text=f"Boundary benchmark record {i}",
        )

    min_res = tools_module.tool_search_updates("Boundary benchmark", limit=1)
    assert min_res["ok"] is True
    assert min_res["count"] == 1

    max_res = tools_module.tool_search_updates(
        "Boundary benchmark",
        limit=tools_module.MAX_SEARCH_LIMIT,
    )
    assert max_res["ok"] is True
    assert max_res["count"] == tools_module.MAX_SEARCH_LIMIT
    assert len(max_res["records"]) == 25


def test_tool_get_sprint_summary_when_no_active_sprint_returns_error(test_db, monkeypatch):
    from app.errors import NotFoundError

    monkeypatch.setattr(
        tools_module,
        "get_sprint_summary",
        lambda: (_ for _ in ()).throw(NotFoundError("Sprint not found.")),
    )

    result = tools_module.tool_get_sprint_summary()
    assert set(result.keys()) == STANDARD_RESULT_KEYS
    assert result["ok"] is False
    assert result["tool"] == "get_sprint_summary"
    assert result["count"] == 0
    assert result["records"] == []
    assert "Sprint not found" in result["error"]


# =========================================================
# 2. Read-Only Guarantee & SQL Safety
# =========================================================


def test_tools_never_mutate_tasks_updates_or_handoffs(test_db):
    save_handoff(
        task_id=test_db["task_id"],
        author_id=test_db["user_id"],
        content="Existing handoff",
        source_update_ids=[test_db["update_id"]],
    )
    tracked_ids = [test_db["task_id"], test_db["done_task_id"]]
    before = _snapshot_db(tracked_ids)

    tools_module.tool_list_tasks()
    tools_module.tool_list_tasks(status="Invalid")
    tools_module.tool_get_task_history(test_db["task_id"])
    tools_module.tool_get_task_history(999999)
    tools_module.tool_search_updates("Initial")
    tools_module.tool_search_updates("")
    tools_module.tool_search_updates("'; DROP TABLE updates; --")
    tools_module.tool_get_sprint_summary()

    after = _snapshot_db(tracked_ids)
    assert after == before


def test_agent_exposes_only_approved_read_only_tools(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "fake-key")
    monkeypatch.setenv("GROQ_MODEL", "fake-model")

    captured = {}

    def fake_create_agent(**kwargs):
        captured.update(kwargs)
        return Mock()

    monkeypatch.setattr(agent_module, "ChatGroq", lambda **kwargs: Mock())
    monkeypatch.setattr(agent_module, "create_agent", fake_create_agent)

    agent_module.create_project_agent()

    exposed_names = {t.name for t in captured["tools"]}
    assert exposed_names == {
        "list_tasks",
        "get_task_history",
        "search_updates",
        "get_sprint_summary",
    }


def test_search_updates_treats_sql_injection_as_literal_text(test_db):
    result = tools_module.tool_search_updates("'; DROP TABLE updates; --")
    assert result["ok"] is True
    assert result["count"] == 0
    assert result["records"] == []

    # Table and records remain intact
    verify = tools_module.tool_get_task_history(test_db["task_id"])
    assert verify["ok"] is True
    assert verify["count"] >= 1


# =========================================================
# 3. Retrieval Relevance, Source Traceability & Conflicts
# =========================================================


def test_search_matches_relevant_records_across_fields_with_exact_source_ids(test_db):
    task_a = create_task(
        title="Auth Migration",
        sprint_id=test_db["sprint_id"],
        assignee_id=test_db["user_id"],
        status="Blocked",
    )

    u_comp = add_update(
        author_id=test_db["user_id"],
        task_id=task_a.id,
        entry_type="progress",
        completed_work="Configured OAuth2 token validator",
    )
    u_block = add_update(
        author_id=test_db["user_id"],
        task_id=task_a.id,
        entry_type="blocker",
        blockers="Blocked by missing Redis cluster credentials",
    )
    u_dec = add_update(
        author_id=test_db["user_id"],
        task_id=None,
        entry_type="decision",
        content="Use JWT bearer flow",
        rationale="Keeps backend services stateless",
    )

    res_oauth = tools_module.tool_search_updates("OAuth2")
    assert res_oauth["ok"] is True
    assert [r["source_id"] for r in res_oauth["records"]] == [f"U-{u_comp.id}"]
    assert res_oauth["records"][0]["task_id"] == task_a.id
    assert res_oauth["records"][0]["task_source_id"] == f"T-{task_a.id}"

    res_redis = tools_module.tool_search_updates("Redis")
    assert res_redis["ok"] is True
    assert [r["source_id"] for r in res_redis["records"]] == [f"U-{u_block.id}"]

    res_stateless = tools_module.tool_search_updates("stateless")
    assert res_stateless["ok"] is True
    assert [r["source_id"] for r in res_stateless["records"]] == [f"U-{u_dec.id}"]
    assert res_stateless["records"][0]["task_id"] is None
    assert res_stateless["records"][0]["task_source_id"] is None

    # Sprint summary blocked task source ID also points to task_a
    summary_res = tools_module.tool_get_sprint_summary()
    blocked_ids = {b["source_id"] for b in summary_res["records"][0]["blocked_tasks"]}
    assert f"T-{task_a.id}" in blocked_ids


def test_empty_search_results_return_clean_empty_payload(test_db):
    result = tools_module.tool_search_updates("xyznonexistenttoken987")
    assert set(result.keys()) == STANDARD_RESULT_KEYS
    assert result["ok"] is True
    assert result["count"] == 0
    assert result["records"] == []
    assert result["error"] is None


def test_conflicting_or_outdated_records_remain_distinct_and_ordered(test_db):
    task = create_task(
        title="Cache Strategy",
        sprint_id=test_db["sprint_id"],
        assignee_id=test_db["user_id"],
    )

    older = add_update(
        author_id=test_db["user_id"],
        task_id=task.id,
        entry_type="decision",
        content="Use in-memory dict cache",
        rationale="Simple initial prototype",
    )
    newer = add_update(
        author_id=test_db["user_id"],
        task_id=task.id,
        entry_type="decision",
        content="Switch to SQLite-backed cache",
        rationale="Supersedes in-memory cache for persistence",
    )

    history_res = tools_module.tool_get_task_history(task.id)
    assert [r["source_id"] for r in history_res["records"]] == [
        f"U-{older.id}",
        f"U-{newer.id}",
    ]

    search_res = tools_module.tool_search_updates("cache")
    returned_ids = [r["source_id"] for r in search_res["records"]]
    assert returned_ids[:2] == [f"U-{newer.id}", f"U-{older.id}"]


# =========================================================
# 4. Grounding & Insufficient Evidence (Mocked Agent Loop)
# =========================================================


def test_agent_grounded_answer_and_insufficient_evidence_with_tool_execution(
    test_db, monkeypatch
):
    """Run ask_agent through a deterministic fake agent executing real read-only tools."""

    class GroundedFakeAgent:
        def invoke(self, inputs):
            question = inputs["messages"][0]["content"]
            if "Redis" in question:
                tool_res = agent_module.search_updates_tool.invoke({"query": "Redis"})
            else:
                tool_res = agent_module.search_updates_tool.invoke(
                    {"query": "UnrecordedTopicXYZ"}
                )

            if tool_res["count"] == 0:
                answer = (
                    "There is insufficient evidence in the recorded project data "
                    "to answer that question."
                )
            else:
                rec = tool_res["records"][0]
                answer = (
                    f"Recorded evidence ({rec['source_id']} on {rec['task_source_id']}): "
                    f"{rec['text']}"
                )

            return {
                "messages": [
                    SimpleNamespace(type="human", content=question),
                    SimpleNamespace(type="tool", content=str(tool_res)),
                    SimpleNamespace(type="ai", content=answer),
                ]
            }

    blocked_task = create_task(
        title="Cache Setup",
        sprint_id=test_db["sprint_id"],
        status="Blocked",
    )
    u = add_update(
        author_id=test_db["user_id"],
        task_id=blocked_task.id,
        entry_type="blocker",
        blockers="Blocked on Redis firewall rule",
    )

    monkeypatch.setattr(
        agent_module,
        "create_project_agent",
        lambda: GroundedFakeAgent(),
    )

    grounded = agent_module.ask_agent("What is blocking Redis?")
    assert f"U-{u.id}" in grounded
    assert f"T-{blocked_task.id}" in grounded
    assert "Blocked on Redis firewall rule" in grounded

    insufficient = agent_module.ask_agent("What is the status of UnrecordedTopicXYZ?")
    assert "insufficient evidence" in insufficient.lower()
    assert f"U-{u.id}" not in insufficient
