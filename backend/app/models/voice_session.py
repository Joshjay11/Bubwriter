"""In-memory voice discovery session storage.

Sessions are kept in-memory for MVP. Each session tracks a single
user's progress through sample analysis → interview → finalization.
Sessions expire after 2 hours.
"""

import time
import uuid
from dataclasses import dataclass, field

SESSION_TTL_SECONDS = 2 * 60 * 60  # 2 hours

# Global session store — keyed by session_id
voice_sessions: dict[str, "VoiceSession"] = {}


@dataclass
class VoiceSession:
    session_id: str
    user_id: str
    writing_sample: str
    style_markers: dict
    interview_messages: list[dict[str, str]] = field(default_factory=list)
    interview_complete: bool = False
    created_at: float = field(default_factory=time.time)

    def is_expired(self) -> bool:
        """Check if this session has exceeded the 2-hour TTL."""
        return (time.time() - self.created_at) > SESSION_TTL_SECONDS


def create_session(user_id: str, writing_sample: str, style_markers: dict) -> str:
    """Create a new voice session and return its ID."""
    cleanup_expired()
    session_id = str(uuid.uuid4())
    voice_sessions[session_id] = VoiceSession(
        session_id=session_id,
        user_id=user_id,
        writing_sample=writing_sample,
        style_markers=style_markers,
    )
    return session_id


def get_session(session_id: str, user_id: str) -> VoiceSession | None:
    """Look up a session, verifying ownership. Returns None if not found or expired."""
    session = voice_sessions.get(session_id)
    if session is None:
        return None
    if session.is_expired():
        voice_sessions.pop(session_id, None)
        return None
    if session.user_id != user_id:
        return None
    return session


def delete_session(session_id: str) -> None:
    """Remove a session after finalization."""
    voice_sessions.pop(session_id, None)


def cleanup_expired() -> None:
    """Remove all expired sessions. Called opportunistically."""
    expired = [sid for sid, s in voice_sessions.items() if s.is_expired()]
    for sid in expired:
        voice_sessions.pop(sid, None)
