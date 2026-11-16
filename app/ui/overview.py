
import streamlit as st

from app.services.sprint_service import get_sprint_summary


def render_overview():
    st.title("Internal Team Agent")
    st.subheader("Project Overview")

    try:
        summary = get_sprint_summary()

        # Sprint information
        st.markdown("### Current Sprint")

        col1, col2 = st.columns(2)

        with col1:
            st.write("**Sprint Goal**")
            st.write(summary.goal)

        with col2:
            st.write("**Sprint Period**")
            st.write(
                f"{summary.start_date} → {summary.end_date}"
            )

        # Task counts
        st.markdown("### Tasks Summary")

        statuses = [
            "To Do",
            "In Progress",
            "Blocked",
            "Done",
        ]

        columns = st.columns(4)

        for column, status in zip(columns, statuses):
            with column:
                count = summary.counts.get(status, 0)
                st.metric(label=status, value=count)

        # Blocked tasks
        st.markdown("### Blocked Tasks")

        if summary.blocked_tasks:
            for task in summary.blocked_tasks:
                st.warning(
                    f"**T-{task['task_id']} — {task['title']}**\n\n"
                    f"Assignee: {task['assignee'] or 'Unassigned'}"
                )
        else:
            st.success("No blocked tasks at the moment.")

    except Exception as e:
        st.error(f"Could not load project overview: {e}")
