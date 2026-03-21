"""In-memory brainstorm session storage.

Same pattern as voice_session.py — in-memory dict with TTL.
Sessions expire after 2 hours.
"""

import time
import uuid
from dataclasses import dataclass, field

SESSION_TTL_SECONDS = 2 * 60 * 60  # 2 hours

# Global session store — keyed by session_id
brainstorm_sessions: dict[str, "BrainstormSession"] = {}


@dataclass
class BrainstormSession:
    session_id: str
    user_id: str
    project_id: str | None
    genre: str | None
    distribution_format: str | None
    conversation_history: list[dict[str, str]] = field(default_factory=list)
    questions_asked: int = 0
    created_at: float = field(default_factory=time.time)

    def is_expired(self) -> bool:
        """Check if this session has exceeded the 2-hour TTL."""
        return (time.time() - self.created_at) > SESSION_TTL_SECONDS


def create_brainstorm_session(
    user_id: str,
    project_id: str | None = None,
    genre: str | None = None,
    distribution_format: str | None = None,
) -> str:
    """Create a new brainstorm session and return its ID."""
    cleanup_expired()
    session_id = str(uuid.uuid4())
    brainstorm_sessions[session_id] = BrainstormSession(
        session_id=session_id,
        user_id=user_id,
        project_id=project_id,
        genre=genre,
        distribution_format=distribution_format,
    )
    return session_id


def get_brainstorm_session(
    session_id: str, user_id: str
) -> BrainstormSession | None:
    """Look up a session, verifying ownership. Returns None if not found or expired."""
    session = brainstorm_sessions.get(session_id)
    if session is None:
        return None
    if session.is_expired():
        brainstorm_sessions.pop(session_id, None)
        return None
    if session.user_id != user_id:
        return None
    return session


def delete_brainstorm_session(session_id: str) -> None:
    """Remove a session."""
    brainstorm_sessions.pop(session_id, None)


def cleanup_expired() -> None:
    """Remove all expired sessions. Called opportunistically."""
    expired = [
        sid for sid, s in brainstorm_sessions.items() if s.is_expired()
    ]
    for sid in expired:
        brainstorm_sessions.pop(sid, None)
