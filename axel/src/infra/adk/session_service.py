import os

from google.adk.sessions import DatabaseSessionService


def get_session_service() -> DatabaseSessionService:
    return DatabaseSessionService(db_url=os.getenv("URL_ADK_SESSIONS"))
