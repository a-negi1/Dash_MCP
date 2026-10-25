import json, os, time
from pathlib import Path
from models import ProjectState

SESSIONS: dict[str, ProjectState] = {}
SESSION_DIR = str(Path(__file__).resolve().parent / '.sessions')
os.makedirs(SESSION_DIR, exist_ok=True)

def get_session(session_id: str) -> ProjectState | None:
    return SESSIONS.get(session_id)

def save_session(state: ProjectState):
    SESSIONS[state.session_id] = state

def require_session(session_id: str) -> ProjectState:
    if session_id not in SESSIONS:
        raise ValueError(f'Session not found: {session_id}')
    return SESSIONS[session_id]

def new_session() -> ProjectState:
    state = ProjectState()
    save_session(state)
    return state
