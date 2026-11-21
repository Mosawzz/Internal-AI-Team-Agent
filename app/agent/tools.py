
from app.services.tasks_service import list_tasks
from app.services.updates_service import get_task_history, search_updates
from app.services.sprint_service import get_sprint_summary
from app.errors import ValidationError, NotFoundError


MAX_SEARCH_LIMIT = 25


def _error_result(tool_name: str, message: str) -> dict:
    """Return a standardized tool error."""
    return {
        "ok": False,
        "tool": tool_name,
        "count": 0,
        "records": [],
        "error": message,
    }


def _success_result(tool_name: str, records: list) -> dict:
    """Return a standardized successful tool result."""
    return {
        "ok": True,
        "tool": tool_name,
        "count": len(records),
        "records": records,
        "error": None,
    }


def _task_to_record(task) -> dict:
    """Convert a Task model into a JSON-serializable record."""
    return {
        "source_id": f"T-{task.id}",
        "kind": "task",
        "task_id": task.id,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "assignee_id": task.assignee_id,
        "sprint_id": task.sprint_id,
        "archived": task.archived,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


def _update_to_record(update) -> dict:
    """Convert an Update model into a JSON-serializable record."""

    text_parts = []

    fields = [
        ("Raw text", update.raw_text),
        ("Completed", update.completed_work),
        ("Remaining", update.remaining_work),
        ("Blockers", update.blockers),
        ("Next step", update.next_step),
        ("Content", update.content),
        ("Rationale", update.rationale),
    ]

    for label, value in fields:
        if value and value.strip():
            text_parts.append(f"{label}: {value.strip()}")

    return {
        "source_id": f"U-{update.id}",
        "kind": "update",
        "task_id": update.task_id,
        "task_source_id": (
            f"T-{update.task_id}" if update.task_id is not None else None
        ),
        "entry_type": update.entry_type,
        "author_id": update.author_id,
        "created_at": update.created_at,
        "text": "; ".join(text_parts),
    }


def tool_list_tasks(
    status: str | None = None,
    assignee_id: int | None = None,
    include_archived: bool = False,
) -> dict:
    """Read tasks with optional status and assignee filters."""

    tool_name = "list_tasks"

    try:
        tasks = list_tasks(
            status=status,
            assignee_id=assignee_id,
            include_archived=include_archived,
        )

        records = [_task_to_record(task) for task in tasks]

        return _success_result(tool_name, records)

    except (ValidationError, NotFoundError) as exc:
        return _error_result(tool_name, str(exc))

    except Exception:
        return _error_result(tool_name, "Unable to retrieve tasks.")


def tool_get_task_history(task_id: int) -> dict:
    """Read the chronological update history of a task."""

    tool_name = "get_task_history"

    try:
        updates = get_task_history(task_id)

        records = [_update_to_record(update) for update in updates]

        return _success_result(tool_name, records)

    except (ValidationError, NotFoundError) as exc:
        return _error_result(tool_name, str(exc))

    except Exception:
        return _error_result(tool_name, "Unable to retrieve task history.")


def tool_search_updates(query: str, limit: int = 10) -> dict:
    """Search stored updates using bounded keyword search."""

    tool_name = "search_updates"

    try:
        if not isinstance(limit, int) or isinstance(limit, bool):
            raise ValidationError("Limit must be an integer.")

        if limit > MAX_SEARCH_LIMIT:
            raise ValidationError(
                f"Limit cannot exceed {MAX_SEARCH_LIMIT}."
            )

        updates = search_updates(query=query, limit=limit)

        records = [_update_to_record(update) for update in updates]

        return _success_result(tool_name, records)

    except (ValidationError, NotFoundError) as exc:
        return _error_result(tool_name, str(exc))

    except Exception:
        return _error_result(tool_name, "Unable to search updates.")


def tool_get_sprint_summary() -> dict:
    """Read the active sprint summary."""

    tool_name = "get_sprint_summary"

    try:
        summary = get_sprint_summary()

        record = {
            "kind": "sprint_summary",
            "sprint_id": summary.sprint_id,
            "goal": summary.goal,
            "start_date": summary.start_date.isoformat(),
            "end_date": summary.end_date.isoformat(),
            "counts": summary.counts,
            "blocked_tasks": [
                {
                    "source_id": f"T-{task['task_id']}",
                    "task_id": task["task_id"],
                    "title": task["title"],
                    "assignee": task["assignee"],
                }
                for task in summary.blocked_tasks
            ],
        }

        return _success_result(tool_name, [record])

    except (ValidationError, NotFoundError) as exc:
        return _error_result(tool_name, str(exc))

    except Exception:
        return _error_result(tool_name, "Unable to retrieve sprint summary.")
