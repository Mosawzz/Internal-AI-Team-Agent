
from app.db.database import SessionLocal
from app.db.models import Handoff, Task, User, Update
from app.errors import ValidationError, NotFoundError


def _validate_id(value, field_name):
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value <= 0
    ):
        raise ValidationError(f"Invalid {field_name}.")


def save_handoff(
    task_id: int,
    author_id: int,
    content: str,
    source_update_ids: list[int]
) -> Handoff:
    """Save an approved handoff for a task."""

    # 1. Validate all inputs before writing to the database
    _validate_id(task_id, "task ID")
    _validate_id(author_id, "author ID")

    if not isinstance(content, str) or not content.strip():
        raise ValidationError("Handoff content cannot be empty.")

    if not isinstance(source_update_ids, list):
        raise ValidationError(
            "source_update_ids must be a list."
        )

    for update_id in source_update_ids:
        _validate_id(update_id, "source update ID")

    if len(source_update_ids) != len(set(source_update_ids)):
        raise ValidationError(
            "Duplicate source update IDs are not allowed."
        )

    db = SessionLocal()

    try:
        # 2. Check that the task exists
        task = db.get(Task, task_id)

        if task is None:
            raise NotFoundError(
                f"Task with ID {task_id} was not found."
            )

        # 3. Check that the author exists
        author = db.get(User, author_id)

        if author is None:
            raise NotFoundError(
                f"User with ID {author_id} was not found."
            )

        # 4. Validate source updates
        if source_update_ids:
            updates = (
                db.query(Update)
                .filter(Update.id.in_(source_update_ids))
                .all()
            )

            found_ids = {update.id for update in updates}

            missing_ids = set(source_update_ids) - found_ids

            if missing_ids:
                raise NotFoundError(
                    f"Source updates not found: {sorted(missing_ids)}"
                )

            for update in updates:
                if update.task_id != task_id:
                    raise ValidationError(
                        f"Update {update.id} does not belong to "
                        f"Task {task_id}."
                    )

        # 5. Create the handoff
        handoff = Handoff(
            task_id=task_id,
            author_id=author_id,
            content=content.strip(),
            status="approved",
            source_update_ids=source_update_ids
        )

        # 6. Save to database
        db.add(handoff)
        db.commit()
        db.refresh(handoff)

        return handoff

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def get_handoffs(task_id: int) -> list[Handoff]:
    """Return all handoffs belonging to a specific task."""

    _validate_id(task_id, "task ID")

    db = SessionLocal()

    try:
        # Check that the task exists
        task = db.get(Task, task_id)

        if task is None:
            raise NotFoundError(
                f"Task with ID {task_id} was not found."
            )

        handoffs = (
            db.query(Handoff)
            .filter(Handoff.task_id == task_id)
            .order_by(Handoff.created_at.desc(), Handoff.id.desc())
            .all()
        )

        return handoffs

    finally:
        db.close()
