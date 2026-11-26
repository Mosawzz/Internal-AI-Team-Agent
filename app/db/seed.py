
from datetime import date

from app.db.database import SessionLocal, init_db
from app.db.models import User, Project, Sprint, Task, Update


def seed_data():
    # Ensure tables exist before any queries
    init_db()

    db = SessionLocal()

    try:
        # 1. Check if the project already exists
        existing_project = db.query(Project).first()

        if existing_project:
            print("Seed data already exists. Skipping...")
            return

        # 2. Create users
        users = [
            User(display_name="Mohamed", role="project_manager"),
            User(display_name="Rahma", role="team_member"),
            User(display_name="Ahmed", role="team_member"),
            User(display_name="Karim", role="team_member"),
            User(display_name="Abdelraheem", role="team_member"),
        ]

        db.add_all(users)
        db.flush()

        # 3. Create project
        project = Project(
            name="Internal Team Agent",
            goal="Build an AI-powered internal team assistant."
        )

        db.add(project)
        db.flush()

        # 4. Create sprint
        sprint = Sprint(
            project_id=project.id,
            goal="Build the MVP database and core services.",
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 30),
            status="active"
        )

        db.add(sprint)
        db.flush()

        # 5. Create tasks
        task_data = [
            ("Set up database", "Configure SQLite and SQLAlchemy.", 1, "Done"),
            ("Create database models", "Define all database entities.", 2, "Done"),
            ("Implement task service", "Create task CRUD operations.", 2, "In Progress"),
            ("Implement update service", "Save and retrieve task updates.", 3, "In Progress"),
            ("Build Streamlit overview", "Create project overview screen.", 3, "To Do"),
            ("Build tasks screen", "Display and filter tasks.", 4, "To Do"),
            ("Test database persistence", "Verify data survives restarts.", 2, "Blocked"),
            ("Implement sprint summary", "Calculate task counts.", 3, "To Do"),
            ("Add error handling", "Handle invalid inputs.", 4, "Blocked"),
            ("Write unit tests", "Test database services.", 2, "To Do"),
        ]

        tasks = []

        for title, description, assignee_index, status in task_data:
            task = Task(
                sprint_id=sprint.id,
                title=title,
                description=description,
                assignee_id=users[assignee_index - 1].id,
                status=status
            )
            tasks.append(task)

        db.add_all(tasks)
        db.flush()

        # 6. Create sample updates
        updates = [
            Update(
                task_id=tasks[0].id,
                author_id=users[0].id,
                entry_type="progress",
                raw_text="Database setup completed successfully.",
                completed_work="SQLite and SQLAlchemy configured.",
                remaining_work="None",
                blockers=None,
                next_step="Continue with service implementation."
            ),
            Update(
                task_id=tasks[2].id,
                author_id=users[1].id,
                entry_type="progress",
                raw_text="Started implementing task service.",
                completed_work="Basic structure created.",
                remaining_work="Implement validation and filtering.",
                blockers=None,
                next_step="Complete task CRUD operations."
            ),
            Update(
                task_id=tasks[6].id,
                author_id=users[2].id,
                entry_type="blocker",
                raw_text="Database persistence test is blocked.",
                blockers="Need to investigate a database connection issue.",
                next_step="Debug the database connection."
            ),
            Update(
                task_id=tasks[3].id,
                author_id=users[1].id,
                entry_type="decision",
                content="Use SQLAlchemy for all database operations.",
                rationale="Keep data access consistent across services."
            ),
            Update(
                task_id=tasks[8].id,
                author_id=users[3].id,
                entry_type="note",
                raw_text="Error handling implementation needs clarification."
            ),
        ]

        db.add_all(updates)

        # 7. Save everything
        db.commit()

        print("Seed data inserted successfully!")

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    seed_data()
