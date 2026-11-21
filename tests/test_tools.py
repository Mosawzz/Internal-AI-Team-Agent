from app.agent import tools as tools_module


def test_tool_list_tasks_success(test_db):
    result = tools_module.tool_list_tasks()

    assert result["ok"] is True
    assert result["tool"] == "list_tasks"
    assert result["error"] is None
    assert result["count"] == 2

    task_ids = [record["task_id"] for record in result["records"]]
    assert test_db["task_id"] in task_ids
    assert test_db["done_task_id"] in task_ids

    task_record = next(
        record for record in result["records"]
        if record["task_id"] == test_db["task_id"]
    )

    assert task_record["source_id"] == f"T-{test_db['task_id']}"
    assert task_record["title"] == "Test Task"
    assert task_record["status"] == "In Progress"


def test_tool_get_task_history_success(test_db):
    result = tools_module.tool_get_task_history(test_db["task_id"])

    assert result["ok"] is True
    assert result["tool"] == "get_task_history"
    assert result["count"] == 1
    assert result["error"] is None

    update_record = result["records"][0]

    assert update_record["source_id"] == f"U-{test_db['update_id']}"
    assert update_record["kind"] == "update"
    assert update_record["task_id"] == test_db["task_id"]
    assert update_record["task_source_id"] == f"T-{test_db['task_id']}"
    assert "Initial test update" in update_record["text"]
    assert "Initial implementation" in update_record["text"]


def test_tool_search_updates_success(test_db):
    result = tools_module.tool_search_updates(
        query="Initial test update",
        limit=10,
    )

    assert result["ok"] is True
    assert result["tool"] == "search_updates"
    assert result["count"] >= 1
    assert result["error"] is None

    matching_record = next(
        record for record in result["records"]
        if record["source_id"] == f"U-{test_db['update_id']}"
    )

    assert "Initial test update" in matching_record["text"]


def test_tool_get_sprint_summary_success(test_db):
    result = tools_module.tool_get_sprint_summary()

    assert result["ok"] is True
    assert result["tool"] == "get_sprint_summary"
    assert result["count"] == 1
    assert result["error"] is None

    summary = result["records"][0]

    assert summary["kind"] == "sprint_summary"
    assert summary["sprint_id"] == test_db["sprint_id"]
    assert summary["goal"] == "Testing sprint"
    assert summary["start_date"] == "2026-11-01"
    assert summary["end_date"] == "2026-11-30"
    assert isinstance(summary["counts"], dict)
    assert isinstance(summary["blocked_tasks"], list)


def test_tool_search_updates_rejects_limit_above_maximum():
    result = tools_module.tool_search_updates(
        query="test",
        limit=26,
    )

    assert result["ok"] is False
    assert result["tool"] == "search_updates"
    assert result["count"] == 0
    assert result["records"] == []
    assert result["error"] is not None
    assert "25" in result["error"]


def test_tool_search_updates_rejects_boolean_limit():
    result = tools_module.tool_search_updates(
        query="test",
        limit=True,
    )

    assert result["ok"] is False
    assert result["tool"] == "search_updates"
    assert result["error"] is not None


def test_tool_get_task_history_returns_error_for_missing_task():
    result = tools_module.tool_get_task_history(99999)

    assert result["ok"] is False
    assert result["tool"] == "get_task_history"
    assert result["count"] == 0
    assert result["records"] == []
    assert result["error"] is not None


def test_tool_error_results_have_standard_structure():
    result = tools_module.tool_search_updates(
        query="test",
        limit=100,
    )

    assert set(result.keys()) == {
        "ok",
        "tool",
        "count",
        "records",
        "error",
    }
