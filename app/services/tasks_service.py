
from app.db.database import SessionLocal
from app.db.models import Task, Sprint, User
from app.errors import ValidationError, NotFoundError


VALID_STATUSES = ["To Do", "In Progress", "Blocked", "Done"]

ALLOWED_UPDATE_FIELDS = {
    "title",
    "description",
    "assignee_id",
    "status",
}


def _validate_status(status):
    """Check that the task status is valid."""
    if status not in VALID_STATUSES:
        raise ValidationError(
            f"Invalid status. Allowed values: {VALID_STATUSES}"
        )


def _validate_title(title):
    """Check that the task title is not empty."""
    if not isinstance(title, str) or not title.strip():
        raise ValidationError("Task title is required.")


def create_task(
    title: str,
    sprint_id: int,
    description: str | None = None,
    assignee_id: int | None = None,
    status: str = "To Do",
) -> Task:
    """Create a new task."""

    # Validate input before writing to the database
    _validate_title(title)
    _validate_status(status)

    if not isinstance(sprint_id, int) or isinstance(sprint_id, bool) or sprint_id <= 0:
        raise ValidationError("A valid sprint_id is required.")

    if assignee_id is not None:
        if not isinstance(assignee_id, int) or isinstance(assignee_id, bool) or assignee_id <= 0:
            raise ValidationError("Invalid assignee_id.")

    db = SessionLocal()

    try:
        # Check that the sprint exists
        sprint = db.get(Sprint, sprint_id)

        if sprint is None:
            raise NotFoundError(f"Sprint with ID {sprint_id} not found.")

        # Check that the assigned user exists
        if assignee_id is not None:
            user = db.get(User, assignee_id)

            if user is None:
                raise NotFoundError(f"User with ID {assignee_id} not found.")

        task = Task(
            title=title.strip(),
            sprint_id=sprint_id,
            description=description,
            assignee_id=assignee_id,
            status=status,
        )

        db.add(task)
        db.commit()
        db.refresh(task)

        return task

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def update_task(task_id: int, **fields) -> Task:
    """Update an existing task."""

    if not isinstance(task_id, int) or isinstance(task_id, bool) or task_id <= 0:
        raise ValidationError("Invalid task_id.")

    # Reject unsupported fields
    invalid_fields = set(fields.keys()) - ALLOWED_UPDATE_FIELDS

    if invalid_fields:
        raise ValidationError(
            f"Fields cannot be updated: {sorted(invalid_fields)}"
        )

    # Validate supplied values before writing
    if "title" in fields:
        _validate_title(fields["title"])

    if "status" in fields:
        _validate_status(fields["status"])

    if "description" in fields:
        description = fields["description"]
        if description is not None and not isinstance(description, str):
            raise ValidationError("Description must be a string or None.")

    if "assignee_id" in fields:
        assignee_id = fields["assignee_id"]

        if assignee_id is not None:
            if not isinstance(assignee_id, int) or isinstance(assignee_id, bool) or assignee_id <= 0:
                raise ValidationError("Invalid assignee_id.")

    db = SessionLocal()

    try:
        task = db.get(Task, task_id)

        if task is None:
            raise NotFoundError(f"Task with ID {task_id} not found.")

        # Check the new assignee if provided
        if fields.get("assignee_id") is not None:
            user = db.get(User, fields["assignee_id"])

            if user is None:
                raise NotFoundError(
                    f"User with ID {fields['assignee_id']} not found."
                )

        for field, value in fields.items():
            if field == "title":
                value = value.strip()

            setattr(task, field, value)

        db.commit()
        db.refresh(task)

        return task

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def get_task(task_id: int) -> Task:
    """Get one task by its ID."""

    if not isinstance(task_id, int) or isinstance(task_id, bool) or task_id <= 0:
        raise ValidationError("Invalid task_id.")

    db = SessionLocal()

    try:
        task = db.get(Task, task_id)

        if task is None:
            raise NotFoundError(f"Task with ID {task_id} not found.")

        return task

    finally:
        db.close()


def list_tasks(
    status: str | None = None,
    assignee_id: int | None = None,
    include_archived: bool = False,
) -> list[Task]:
    """List tasks with optional filters."""

    if status is not None:
        _validate_status(status)

    if not isinstance(include_archived, bool):
        raise ValidationError("include_archived must be True or False.")

    if assignee_id is not None:
        if not isinstance(assignee_id, int) or isinstance(assignee_id, bool) or assignee_id <= 0:
            raise ValidationError("Invalid assignee_id.")

    db = SessionLocal()

    try:
        query = db.query(Task)

        if status is not None:
            query = query.filter(Task.status == status)

        if assignee_id is not None:
            query = query.filter(Task.assignee_id == assignee_id)

        if not include_archived:
            query = query.filter(Task.archived == False)

        return query.order_by(Task.id).all()

    finally:
        db.close()


def archive_task(task_id: int) -> Task:
    """Archive a task only when its status is Done."""

    if not isinstance(task_id, int) or isinstance(task_id, bool) or task_id <= 0:
        raise ValidationError("Invalid task_id.")

    db = SessionLocal()

    try:
        task = db.get(Task, task_id)

        if task is None:
            raise NotFoundError(f"Task with ID {task_id} not found.")

        if task.status != "Done":
            raise ValidationError(
                "Only tasks with status 'Done' can be archived."
            )

        task.archived = True

        db.commit()
        db.refresh(task)

        return task

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()
