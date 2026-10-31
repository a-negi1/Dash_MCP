import json, os, time
from pathlib import Path
from models import ProjectState

SESSIONS: dict[str, ProjectState] = {}
SESSION_DIR = os.getenv(
    "SESSION_DIR",
    str(Path(__file__).resolve().parent / ".sessions"),
)
TTL_SECONDS = 7200  # 2 hours

os.makedirs(SESSION_DIR, exist_ok=True)

def get_session(session_id: str) -> ProjectState | None:
    if session_id in SESSIONS:
        s = SESSIONS[session_id]
        if time.time() - s.updated_at < TTL_SECONDS:
            return s
        else:
            del SESSIONS[session_id]
            return None
    path = f"{SESSION_DIR}/{session_id}.json"
    if os.path.exists(path):
        with open(path) as f:
            return ProjectState(**json.load(f))
    return None

def save_session(state: ProjectState):
    state.updated_at = time.time()
    SESSIONS[state.session_id] = state
    path = f"{SESSION_DIR}/{state.session_id}.json"
    with open(path, "w") as f:
        f.write(state.model_dump_json(indent=2))

def require_session(session_id: str) -> ProjectState:
    state = get_session(session_id)
    if not state:
        raise ValueError(f"Session not found or expired: {session_id}")
    return state

def new_session() -> ProjectState:
    state = ProjectState()
    save_session(state)
    return state
