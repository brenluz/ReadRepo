import secrets
from typing import TypedDict


class SessionData(TypedDict):
    access_token: str
    github_login: str


class SessionStore:
    """
    Minimal server-side session store.

    This is deliberately a dict wrapped in a class, not just a bare
    module-level dict, so that every place in the app that touches
    sessions goes through create/get/delete methods rather than
    reaching into a global dict directly. That means swapping this
    for a Redis-backed version later is a one-file change: same
    method signatures, different __init__ / storage backend.

    NOTE: an in-memory dict means sessions vanish on server restart,
    and this won't work if you ever run multiple server processes
    (each process gets its own dict). Fine for local dev; Redis (or
    any shared store) is the fix once you deploy with >1 worker.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, SessionData] = {}

    def create(self, data: SessionData) -> str:
        session_id = secrets.token_urlsafe(32)
        self._sessions[session_id] = data
        return session_id

    def get(self, session_id: str) -> SessionData | None:
        return self._sessions.get(session_id)

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)


# Single shared instance for the app's lifetime.
session_store = SessionStore()