"""One SilverFile service for the whole web app. Owner: Supriya Patil.

SUMMARY FOR THE TEAM
In one line: the taxpayer chat page and the volunteer dashboard share ONE W-2 service and graph.

What it does:
  - Builds JiWon's shared W-2 service (src/p3/shared_service.py) once, on the saved sessions,
    and keeps it for as long as the app runs. Both pages call get_service(), so a photo the
    taxpayer adds and a W-2 reading a volunteer approves go through the same graph with the
    W-2 tools registered (Francesca's note in make_shared_service).

What is still missing:
  - Nothing; the logic is in src/ui/chat_session.py (make_app_service) and dashboard_data.py.
"""
import streamlit as st

from src.ui import dashboard_data as dash


@st.cache_resource
def get_service():
    """The app's one service; cached so every page and every visitor shares it."""
    return dash.open_service()
