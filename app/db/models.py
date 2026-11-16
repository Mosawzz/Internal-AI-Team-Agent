
from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    JSON,
    String,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


# ==========================================
# 1. Base Class
# ==========================================

class Base(DeclarativeBase):
    pass


# ==========================================
# 2. Timestamp Helper
# ==========================================

def utc_now_iso() -> str:
    """Return current UTC time as an ISO-8601 string."""
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )


# ==========================================
# 3. User Model
# ==========================================

class User(Base):
    __tablename__ = "users"

    __table_args__ = (
        CheckConstraint(
            "role IN ('team_member', 'project_manager')",
            name="ck_users_role",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    display_name: Mapped[str] = mapped_column(
        String(100), nullable=False
    )

    role: Mapped[str] = mapped_column(
        String(30), nullable=False
    )

    # Relationships
    assigned_tasks: Mapped[list["Task"]] = relationship(
        back_populates="assignee"
    )

    updates: Mapped[list["Update"]] = relationship(
        back_populates="author"
    )

    handoffs: Mapped[list["Handoff"]] = relationship(
        back_populates="author"
    )


# ==========================================
# 4. Project Model
# ==========================================

class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    name: Mapped[str] = mapped_column(
        String(200), nullable=False
    )

    goal: Mapped[str] = mapped_column(
        String, nullable=False, default=""
    )

    # Relationships
    sprints: Mapped[list["Sprint"]] = relationship(
        back_populates="project"
    )


# ==========================================
# 5. Sprint Model
# ==========================================

class Sprint(Base):
    __tablename__ = "sprints"

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'closed')",
            name="ck_sprints_status",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id"),
        nullable=False
    )

    goal: Mapped[str] = mapped_column(
        String, nullable=False, default=""
    )

    start_date: Mapped[date] = mapped_column(
        Date, nullable=False
    )

    end_date: Mapped[date] = mapped_column(
        Date, nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active"
    )

    # Relationships
    project: Mapped["Project"] = relationship(
        back_populates="sprints"
    )

    tasks: Mapped[list["Task"]] = relationship(
        back_populates="sprint"
    )


# ==========================================
# 6. Task Model
# ==========================================

class Task(Base):
    __tablename__ = "tasks"

    __table_args__ = (
        CheckConstraint(
            "status IN ('To Do', 'In Progress', 'Blocked', 'Done')",
            name="ck_tasks_status",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    sprint_id: Mapped[int] = mapped_column(
        ForeignKey("sprints.id"),
        nullable=False
    )

    title: Mapped[str] = mapped_column(
        String(200), nullable=False
    )

    description: Mapped[str | None] = mapped_column(
        String, nullable=True
    )

    assignee_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True
    )

    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="To Do"
    )

    archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    created_at: Mapped[str] = mapped_column(
        String(20), nullable=False, default=utc_now_iso
    )

    updated_at: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=utc_now_iso,
        onupdate=utc_now_iso,
    )

    # Relationships
    sprint: Mapped["Sprint"] = relationship(
        back_populates="tasks"
    )

    assignee: Mapped["User | None"] = relationship(
        back_populates="assigned_tasks"
    )

    updates: Mapped[list["Update"]] = relationship(
        back_populates="task"
    )

    handoffs: Mapped[list["Handoff"]] = relationship(
        back_populates="task"
    )


# ==========================================
# 7. Update Model
# ==========================================

class Update(Base):
    __tablename__ = "updates"

    __table_args__ = (
        CheckConstraint(
            "entry_type IN ('progress', 'decision', 'blocker', 'note')",
            name="ck_updates_entry_type",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id"),
        nullable=True
    )

    author_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False
    )

    entry_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )

    raw_text: Mapped[str | None] = mapped_column(
        String, nullable=True
    )

    completed_work: Mapped[str | None] = mapped_column(
        String, nullable=True
    )

    remaining_work: Mapped[str | None] = mapped_column(
        String, nullable=True
    )

    blockers: Mapped[str | None] = mapped_column(
        String, nullable=True
    )

    next_step: Mapped[str | None] = mapped_column(
        String, nullable=True
    )

    content: Mapped[str | None] = mapped_column(
        String, nullable=True
    )

    rationale: Mapped[str | None] = mapped_column(
        String, nullable=True
    )

    created_at: Mapped[str] = mapped_column(
        String(20), nullable=False, default=utc_now_iso
    )

    # Relationships
    task: Mapped["Task | None"] = relationship(
        back_populates="updates"
    )

    author: Mapped["User"] = relationship(
        back_populates="updates"
    )


# ==========================================
# 8. Handoff Model
# ==========================================

class Handoff(Base):
    __tablename__ = "handoffs"

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'approved')",
            name="ck_handoffs_status",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id"),
        nullable=False
    )

    author_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False
    )

    content: Mapped[str] = mapped_column(
        String, nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(20), nullable=False
    )

    source_update_ids: Mapped[list[int]] = mapped_column(
        JSON, nullable=False, default=list
    )

    created_at: Mapped[str] = mapped_column(
        String(20), nullable=False, default=utc_now_iso
    )

    # Relationships
    task: Mapped["Task"] = relationship(
        back_populates="handoffs"
    )

    author: Mapped["User"] = relationship(
        back_populates="handoffs"
    )
