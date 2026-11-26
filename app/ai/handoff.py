
from pydantic import BaseModel, Field

from app.errors import ValidationError
from app.services.tasks_service import get_task
from app.services.updates_service import get_task_history


PLACEHOLDER_VALUES = {"none", "n/a", "unknown", "not recorded"}


class HandoffDraft(BaseModel):
    current_status: str | None = None
    completed_work: list[str] = Field(default_factory=list)
    remaining_work: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)


def _validate_task_id(task_id):
    if (
        not isinstance(task_id, int)
        or isinstance(task_id, bool)
        or task_id <= 0
    ):
        raise ValidationError("Invalid task ID.")


def _as_list(value) -> list[str]:
    """Normalize a stored text field into a list of facts."""

    if value is None:
        return []

    if isinstance(value, str):
        items = value.splitlines()
    elif isinstance(value, (list, tuple)):
        items = list(value)
    else:
        items = [value]

    result = []

    for item in items:
        text = str(item).strip()

        if text and text.lower() not in PLACEHOLDER_VALUES:
            result.append(text)

    return result


def _extend_unique(target: list[str], values: list[str]) -> None:
    """Append values while keeping order and removing duplicates."""

    seen = {item.lower() for item in target}

    for value in values:
        key = value.lower()

        if key not in seen:
            seen.add(key)
            target.append(value)


def generate_handoff_draft(task_id: int) -> HandoffDraft:
    """Build a handoff draft from recorded task facts only.

    This function is read-only: it never changes task state or assignments.
    Missing information is left empty instead of being invented.
    """

    _validate_task_id(task_id)

    task = get_task(task_id)
    history = get_task_history(task_id)

    completed_work = []
    remaining_work = []
    blockers = []
    decisions = []
    next_steps = []

    for update in history:
        _extend_unique(
            completed_work,
            _as_list(update.completed_work),
        )
        _extend_unique(
            remaining_work,
            _as_list(update.remaining_work),
        )
        _extend_unique(
            blockers,
            _as_list(update.blockers),
        )
        _extend_unique(
            next_steps,
            _as_list(update.next_step),
        )

        if update.entry_type == "blocker" and not update.blockers:
            _extend_unique(
                blockers,
                _as_list(update.raw_text),
            )

        if update.entry_type == "decision":
            decision = (update.content or "").strip()
            rationale = (update.rationale or "").strip()

            if decision:
                if rationale:
                    decision = f"{decision} (Rationale: {rationale})"

                _extend_unique(decisions, [decision])

    return HandoffDraft(
        current_status=task.status,
        completed_work=completed_work,
        remaining_work=remaining_work,
        blockers=blockers,
        decisions=decisions,
        next_steps=next_steps,
        source_ids=[f"T-{task_id}"] + [
            f"U-{update.id}"
            for update in history
        ],
    )


def render_handoff_draft(draft: HandoffDraft) -> str:
    """Render a draft as editable review text."""

    sections = [
        (
            "Current Status",
            [draft.current_status] if draft.current_status else [],
        ),
        ("Completed Work", draft.completed_work),
        ("Remaining Work", draft.remaining_work),
        ("Blockers", draft.blockers),
        ("Decisions", draft.decisions),
        ("Next Steps", draft.next_steps),
    ]

    lines = []

    for title, items in sections:
        lines.append(f"{title}:")

        if items:
            lines.extend(f"- {item}" for item in items)
        else:
            lines.append("- Not recorded")

        lines.append("")

    lines.append("Sources: " + ", ".join(draft.source_ids))

    return "\n".join(lines).strip()
