
import streamlit as st

from app.db.database import init_db
from app.ui.overview import render_overview
from app.ui.tasks_updates import render_tasks_updates

def main():
    st.set_page_config(
        page_title="Internal Team Agent",
        page_icon="🤖",
        layout="wide",
    )

    # Initialize database
    init_db()

    # Sidebar navigation
    st.sidebar.title("Navigation")

    page = st.sidebar.radio(
        "Go to",
        ["Project Overview", "Tasks & Updates"],
    )

    if page == "Project Overview":
        render_overview()
        
    elif page == "Tasks & Updates":
        render_tasks_updates()


if __name__ == "__main__":
    main()
