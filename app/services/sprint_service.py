
from dataclasses import dataclass
from datetime import date

from app.db.database import SessionLocal
from app.db.models import Sprint, Task, User
from app.errors import ValidationError, NotFoundError


VALID_STATUSES = ["To Do", "In Progress", "Blocked", "Done"]


@dataclass
class SprintSummary:
    sprint_id: int
    goal: str
    start_date: date
    end_date: date
    counts: dict[str, int]
    blocked_tasks: list[dict]


def get_sprint_summary(sprint_id: int | None = None) -> SprintSummary:
    """
    Return a summary of a sprint.

    If sprint_id is None, use the active sprint.
    """

    # 1. Validate sprint ID
    if sprint_id is not None:
        if (
            not isinstance(sprint_id, int)
            or isinstance(sprint_id, bool)
            or sprint_id <= 0
        ):
            raise ValidationError("Invalid sprint_id.")

    db = SessionLocal()

    try:
        # 2. Get the requested sprint
        if sprint_id is not None:
            sprint = db.get(Sprint, sprint_id)
        else:
            sprint = (
                db.query(Sprint)
                .filter(Sprint.status == "active")
                .order_by(Sprint.id)
                .first()
            )

        if sprint is None:
            raise NotFoundError("Sprint not found.")

        # 3. Initialize all status counts with zero
        counts = {
            status: 0
            for status in VALID_STATUSES
        }

        # 4. Get non-archived tasks belonging to this sprint
        tasks = (
            db.query(Task)
            .filter(
                Task.sprint_id == sprint.id,
                Task.archived == False,
            )
            .all()
        )

        # 5. Count tasks by status
        for task in tasks:
            counts[task.status] += 1

        # 6. Collect blocked tasks
        blocked_tasks = []

        for task in tasks:
            if task.status == "Blocked":
                assignee = None

                if task.assignee_id is not None:
                    user = db.get(User, task.assignee_id)

                    if user is not None:
                        assignee = user.display_name

                blocked_tasks.append({
                    "task_id": task.id,
                    "title": task.title,
                    "assignee": assignee,
                })

        # 7. Build the summary
        return SprintSummary(
            sprint_id=sprint.id,
            goal=sprint.goal,
            start_date=sprint.start_date,
            end_date=sprint.end_date,
            counts=counts,
            blocked_tasks=blocked_tasks,
        )

    finally:
        db.close()
