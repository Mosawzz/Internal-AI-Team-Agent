import streamlit as st
from app.services.updates_service import get_task_history
from app.services.users_service import list_users
from app.services.updates_service import add_update
from app.services.tasks_service import (
    list_tasks,
    get_task,
    archive_task,
    create_task,
    update_task,
)
from app.services.sprint_service import get_sprint_summary


STATUSES = [
    "All",
    "To Do",
    "In Progress",
    "Blocked",
    "Done",
]


def render_tasks_updates():
    st.title("Tasks & Updates")
    st.write("View tasks, filter them, and inspect their update history.")

    try:
        users = list_users()
        user_names = {
            user.id: user.display_name
            for user in users
        }

        # Create Task
        st.divider()
        st.markdown("### Create New Task")

        project_managers = [
            user for user in users
            if user.role == "project_manager"
        ]

        if not project_managers:
            st.warning("No Project Manager found.")

        else:
            st.caption("Project Manager: " + ", ".join(
                user.display_name for user in project_managers
            ))

            current_sprint = get_sprint_summary()

            assignee_options = {
                "Unassigned": None,
                **{
                    user.display_name: user.id
                    for user in users
                },
            }

            with st.form("create_task_form"):

                new_title = st.text_input("Task Title")

                new_description = st.text_area(
                    "Task Description"
                )

                new_assignee = st.selectbox(
                    "Assign To",
                    list(assignee_options.keys()),
                )

                new_status = st.selectbox(
                    "Initial Status",
                    ["To Do", "In Progress", "Blocked", "Done"],
                )

                submit_task = st.form_submit_button(
                    "Create Task"
                )

                if submit_task:
                    if not new_title.strip():
                        st.warning("Task title is required.")

                    else:
                        try:
                            create_task(
                                title=new_title.strip(),
                                sprint_id=current_sprint.sprint_id,
                                description=new_description.strip() or None,
                                assignee_id=assignee_options[new_assignee],
                                status=new_status,
                            )

                            st.success("Task created successfully!")
                            st.rerun()

                        except Exception as e:
                            st.error(f"Could not create task: {e}")

        # Filters
        st.markdown("### Filter Tasks")

        col1, col2, col3 = st.columns(3)

        with col1:
            selected_status = st.selectbox(
                "Status",
                STATUSES,
            )

        with col2:
            assignee_options = {
                "All": None,
                **{
                    user.display_name: user.id
                    for user in users
                },
            }

            selected_assignee = st.selectbox(
                "Assignee",
                list(assignee_options.keys()),
            )

        with col3:
            include_archived = st.checkbox(
                "Include archived tasks",
                value=False,
            )

        # Load tasks
        tasks = list_tasks(
            status=(
                None if selected_status == "All"
                else selected_status
            ),
            assignee_id=assignee_options[selected_assignee],
            include_archived=include_archived,
        )

        st.markdown("### Tasks List")

        if not tasks:
            st.info("No tasks found with the selected filters.")
            return

        # Display tasks
        for task in tasks:
            assignee_name = user_names.get(
                task.assignee_id,
                "Unassigned",
            )

            with st.container(border=True):
                col1, col2 = st.columns([3, 1])

                with col1:
                    st.markdown(
                        f"**T-{task.id} — {task.title}**"
                    )
                    st.write(f"Assignee: {assignee_name}")

                with col2:
                    st.write(f"Status: **{task.status}**")

        # Task details
        st.divider()
        st.markdown("### Task Details")

        task_options = {
            f"T-{task.id} — {task.title}": task.id
            for task in tasks
        }

        selected_task_label = st.selectbox(
            "Select a task",
            list(task_options.keys()),
        )

        task_id = task_options[selected_task_label]

        task = get_task(task_id)
        history = get_task_history(task_id)

        st.markdown(f"#### T-{task.id} — {task.title}")
        st.write(f"**Status:** {task.status}")
        st.write(
            f"**Assignee:** "
            f"{user_names.get(task.assignee_id, 'Unassigned')}"
        )

        if task.description:
            st.write(f"**Description:** {task.description}")

        # Edit Task
        st.divider()
        st.markdown("### Edit Task")

        edit_assignee_options = {
            "Unassigned": None,
            **{
                user.display_name: user.id
                for user in users
            },
        }

        current_assignee = next(
            (
                user.display_name
                for user in users
                if user.id == task.assignee_id
            ),
            "Unassigned",
        )

        status_options = [
            "To Do",
            "In Progress",
            "Blocked",
            "Done",
        ]

        with st.form("edit_task_form"):

            edited_title = st.text_input(
                "Task Title",
                value=task.title,
                key=f"edit_title_{task.id}",
            )

            edited_description = st.text_area(
                "Task Description",
                value=task.description or "",
                key=f"edit_description_{task.id}",
            )

            edited_assignee = st.selectbox(
                "Assign To",
                options=list(edit_assignee_options.keys()),
                index=list(edit_assignee_options.keys()).index(
                    current_assignee
                ),
                key=f"edit_assignee_{task.id}",
            )

            edited_status = st.selectbox(
                "Status",
                options=status_options,
                index=status_options.index(task.status),
                key=f"edit_status_{task.id}",
            )

            submit_edit = st.form_submit_button(
                "Save Changes"
            )

            if submit_edit:

                if not edited_title.strip():
                    st.warning("Task title is required.")

                else:
                    try:
                        update_task(
                            task_id=task.id,
                            title=edited_title.strip(),
                            description=edited_description.strip() or None,
                            assignee_id=edit_assignee_options[
                                edited_assignee
                            ],
                            status=edited_status,
                        )

                        st.success("Task updated successfully!")
                        st.rerun()

                    except Exception as e:
                        st.error(f"Could not update task: {e}")

        # Update history
        st.markdown("### Update History")

        if history:
            for update in history:
                with st.container(border=True):
                    st.write(
                        f"**{update.entry_type.title()}**"
                    )

                    if update.raw_text:
                        st.write(update.raw_text)

                    if update.content:
                        st.write(update.content)

                    if update.rationale:
                        st.write(
                            f"**Rationale:** {update.rationale}"
                        )

                    st.caption(
                        f"Update ID: U-{update.id} | "
                        f"Author ID: {update.author_id} | "
                        f"{update.created_at}"
                    )
        else:
            st.info("No updates have been recorded for this task yet.")

        # Add manual progress update
        st.divider()
        st.markdown("### Add Manual Progress Update")
        author_options = {
            user.display_name: user.id
            for user in users
        }
        with st.form("manual_progress_form"):
            selected_author = st.selectbox(
                "Author",
                list(author_options.keys()),
                key="progress_author",
            )
            completed_work = st.text_area(
                "Completed Work",
                key="completed_work",
            )
            remaining_work = st.text_area(
                "Remaining Work",
                key="remaining_work",
            )
            blockers = st.text_area(
                "Blockers",
                key="progress_blockers",
            )
            next_step = st.text_area(
                "Next Step",
                key="next_step",
            )

        # Record decision
        st.markdown("### Record Decision")
        with st.form("decision_form"):
            decision_author = st.selectbox(
                "Author",
                list(author_options.keys()),
                key="decision_author",
            )
            decision_content = st.text_area(
                "Decision",
                key="decision_content",
            )
            decision_rationale = st.text_area(
                "Rationale",
                key="decision_rationale",
            )
            submit_decision = st.form_submit_button(
                "Save Decision"
            )
            if submit_decision:
                if not decision_content.strip():
                    st.warning("Decision content is required.")
                else:
                    try:
                        add_update(
                            author_id=author_options[decision_author],
                            entry_type="decision",
                            task_id=task_id,
                            content=decision_content.strip(),
                            rationale=decision_rationale.strip() or None,
                        )
                        st.success("Decision saved successfully!")
                    except Exception as e:
                        st.error(f"Could not save decision: {e}")

        # Archive Task
        st.divider()
        st.markdown("### Archive Task")

        if task.archived:
            st.info("This task is already archived.")

        elif task.status != "Done":
            st.info("Only tasks with status Done can be archived.")

        else:
            if st.button("Archive This Task"):
                try:
                    archive_task(task_id)

                    st.success("Task archived successfully!")
                    st.rerun()

                except Exception as e:
                    st.error(f"Could not archive task: {e}")

    except Exception as e:
        st.error(f"Could not load Tasks & Updates: {e}")