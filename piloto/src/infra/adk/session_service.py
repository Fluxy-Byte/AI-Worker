import os

from google.adk.sessions import DatabaseSessionService

"""
Essa função tem como foco devolver o metodo de runtime do adk para chamar funcionalidades da biblioteca ADK
"""

def get_session_service() -> DatabaseSessionService:
    return DatabaseSessionService(db_url=os.getenv("URL_ADK_SESSIONS"))
