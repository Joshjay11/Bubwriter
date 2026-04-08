"""In-memory Story DNA Analyzer session storage.

Anonymous sessions for the personality-based DNA Analyzer (Step 0 of the
BUB Writer flow). Sessions live for 2 hours so a user has time to take
the test, walk through signup, and migrate the session to persistent
storage afterwards.

TODO: When BUB Writer scales to multiple backend instances, move this
store to Redis so sessions survive container restarts and are visible
across replicas. The current dict + in-process IP limiter only works
for single-instance Railway deployments.
"""

import time
import uuid
from dataclasses import dataclass, field

SESSION_TTL_SECONDS = 2 * 60 * 60  # 2 hours
RATE_LIMIT_WINDOW_SECONDS = 24 * 60 * 60  # 24 hours
RATE_LIMIT_MAX_SESSIONS = 3  # per IP per window

# Global stores — single-instance only (see TODO above)
story_dna_sessions: dict[str, "StoryDnaSession"] = {}
_ip_session_log: dict[str, list[float]] = {}


@dataclass
class StoryDnaSession:
    session_id: str
    ip: str
    turns: list[dict[str, str]] = field(default_factory=list)
    question_count: int = 0
    voice_signal: dict | None = None
    finalized: bool = False
    dna_profile: dict | None = None
    concepts: list[dict] | None = None
    migrated_user_ids: dict[str, str] = field(default_factory=dict)  # user_id -> dna_profile_id
    created_at: float = field(default_factory=time.time)

    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > SESSION_TTL_SECONDS


def cleanup_expired() -> None:
    """Drop expired sessions and prune the IP rate-limit log."""
    now = time.time()
    expired = [sid for sid, s in story_dna_sessions.items() if s.is_expired()]
    for sid in expired:
        story_dna_sessions.pop(sid, None)

    cutoff = now - RATE_LIMIT_WINDOW_SECONDS
    for ip in list(_ip_session_log.keys()):
        recent = [t for t in _ip_session_log[ip] if t >= cutoff]
        if recent:
            _ip_session_log[ip] = recent
        else:
            _ip_session_log.pop(ip, None)


def check_rate_limit(ip: str) -> bool:
    """Return True if this IP can start a new session, False if over the limit."""
    cleanup_expired()
    now = time.time()
    cutoff = now - RATE_LIMIT_WINDOW_SECONDS
    recent = [t for t in _ip_session_log.get(ip, []) if t >= cutoff]
    return len(recent) < RATE_LIMIT_MAX_SESSIONS


def record_session_start(ip: str) -> None:
    """Log a session start for IP rate-limit accounting."""
    _ip_session_log.setdefault(ip, []).append(time.time())


def create_session(ip: str) -> "StoryDnaSession":
    """Create and register a new anonymous Story DNA session."""
    session_id = f"sdna_{uuid.uuid4().hex}"
    session = StoryDnaSession(session_id=session_id, ip=ip)
    story_dna_sessions[session_id] = session
    record_session_start(ip)
    return session


def get_session(session_id: str) -> StoryDnaSession | None:
    """Look up an anonymous session. Returns None if missing or expired."""
    session = story_dna_sessions.get(session_id)
    if session is None:
        return None
    if session.is_expired():
        story_dna_sessions.pop(session_id, None)
        return None
    return session


def delete_session(session_id: str) -> None:
    story_dna_sessions.pop(session_id, None)
