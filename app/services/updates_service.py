
from sqlalchemy import or_

from app.db.database import SessionLocal
from app.db.models import Update, Task, User
from app.errors import ValidationError, NotFoundError


VALID_ENTRY_TYPES = ["progress", "decision", "blocker", "note"]

SEARCHABLE_FIELDS = [
    Update.raw_text,
    Update.completed_work,
    Update.remaining_work,
    Update.blockers,
    Update.next_step,
    Update.content,
    Update.rationale,
]


def _validate_id(value, field_name):
    """Validate a positive integer ID."""
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValidationError(f"Invalid {field_name}.")


def _validate_optional_text(value, field_name):
    """Validate an optional text field."""
    if value is not None and not isinstance(value, str):
        raise ValidationError(f"{field_name} must be a string or None.")


def add_update(
    author_id: int,
    entry_type: str,
    task_id: int | None = None,
    raw_text: str | None = None,
    completed_work: str | None = None,
    remaining_work: str | None = None,
    blockers: str | None = None,
    next_step: str | None = None,
    content: str | None = None,
    rationale: str | None = None,
) -> Update:
    """Create and save a new update."""

    # 1. Validate inputs before database writes
    _validate_id(author_id, "author_id")

    if entry_type not in VALID_ENTRY_TYPES:
        raise ValidationError(
            f"Invalid entry_type. Allowed values: {VALID_ENTRY_TYPES}"
        )

    if task_id is not None:
        _validate_id(task_id, "task_id")

    text_fields = {
        "raw_text": raw_text,
        "completed_work": completed_work,
        "remaining_work": remaining_work,
        "blockers": blockers,
        "next_step": next_step,
        "content": content,
        "rationale": rationale,
    }

    for field_name, value in text_fields.items():
        _validate_optional_text(value, field_name)

    # 2. Open database session
    db = SessionLocal()

    try:
        # 3. Verify author exists
        author = db.get(User, author_id)

        if author is None:
            raise NotFoundError(
                f"User with ID {author_id} not found."
            )

        # 4. Verify task exists if task_id was provided
        if task_id is not None:
            task = db.get(Task, task_id)

            if task is None:
                raise NotFoundError(
                    f"Task with ID {task_id} not found."
                )

        # 5. Create update
        update = Update(
            author_id=author_id,
            task_id=task_id,
            entry_type=entry_type,
            raw_text=raw_text,
            completed_work=completed_work,
            remaining_work=remaining_work,
            blockers=blockers,
            next_step=next_step,
            content=content,
            rationale=rationale,
        )

        db.add(update)
        db.commit()
        db.refresh(update)

        return update

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def get_task_history(task_id: int) -> list[Update]:
    """Return task updates from oldest to newest."""

    _validate_id(task_id, "task_id")

    db = SessionLocal()

    try:
        # Check whether the task exists
        task = db.get(Task, task_id)

        if task is None:
            raise NotFoundError(
                f"Task with ID {task_id} not found."
            )

        # Retrieve updates in chronological order
        updates = (
            db.query(Update)
            .filter(Update.task_id == task_id)
            .order_by(Update.created_at.asc(), Update.id.asc())
            .all()
        )

        return updates

    finally:
        db.close()


def search_updates(query: str, limit: int = 10) -> list[Update]:
    """Search update text using bounded keyword LIKE."""

    # 1. Validate search query
    if not isinstance(query, str) or not query.strip():
        raise ValidationError("Search query cannot be empty.")

    # 2. Validate result limit
    if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
        raise ValidationError("Limit must be a positive integer.")

    search_term = query.strip()

    db = SessionLocal()

    try:
        # Search across all user-visible update text fields
        conditions = [
            field.like(f"%{search_term}%")
            for field in SEARCHABLE_FIELDS
        ]

        updates = (
            db.query(Update)
            .filter(or_(*conditions))
            .order_by(Update.created_at.desc(), Update.id.desc())
            .limit(limit)
            .all()
        )

        return updates

    finally:
        db.close()
