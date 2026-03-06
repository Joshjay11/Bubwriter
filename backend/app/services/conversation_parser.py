"""ChatGPT export ZIP parser — extracts user messages from conversation history.

Accepts a ChatGPT data export (ZIP containing conversations.json), walks the
conversation tree structure, and returns a flat list of user messages with
metadata. Processes entirely in memory — no disk writes.

Privacy: raw conversation content is returned to the caller for filtering
and analysis, then discarded. Nothing is persisted by this module.
"""

import io
import json
import logging
import zipfile
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def parse_chatgpt_export(file_contents: bytes) -> list[dict]:
    """Extract user messages from a ChatGPT export ZIP.

    Args:
        file_contents: Raw bytes of the uploaded ZIP file.

    Returns:
        List of message dicts with keys:
            role, content, timestamp, conversation_title, word_count

    Raises:
        ValueError: If the file is not a valid ZIP, missing conversations.json,
                    or contains no parseable conversations.
    """
    try:
        zip_buffer = io.BytesIO(file_contents)
        zf = zipfile.ZipFile(zip_buffer)
    except zipfile.BadZipFile:
        raise ValueError(
            "The uploaded file is not a valid ZIP archive. "
            "Please upload the ZIP file you received from ChatGPT."
        )

    # Locate conversations.json — may be at root or in a subdirectory
    conversations_path = _find_conversations_json(zf)
    if conversations_path is None:
        raise ValueError(
            "No conversations.json found in the ZIP. "
            "Please upload the original ChatGPT data export without modification."
        )

    try:
        raw = zf.read(conversations_path)
        conversations = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(
            "conversations.json is corrupted or unreadable. "
            "Please re-export your data from ChatGPT."
        ) from exc

    if not isinstance(conversations, list) or len(conversations) == 0:
        raise ValueError(
            "The export contains no conversations. "
            "Please make sure you've had some conversations before exporting."
        )

    messages = _extract_user_messages(conversations)

    if len(messages) == 0:
        raise ValueError(
            "No user messages could be extracted from the export. "
            "The file may use an unsupported format."
        )

    logger.info(
        "Parsed ChatGPT export: %d conversations, %d user messages",
        len(conversations),
        len(messages),
    )

    return messages


def _find_conversations_json(zf: zipfile.ZipFile) -> str | None:
    """Locate conversations.json inside the ZIP, handling nested paths."""
    for name in zf.namelist():
        if name.endswith("conversations.json"):
            return name
    return None


def _extract_user_messages(conversations: list[dict]) -> list[dict]:
    """Walk each conversation's message tree and extract user messages.

    ChatGPT exports use a mapping structure where each node has a parent
    pointer. We walk from roots to leaves, collecting user messages.
    Handles both the current (2024-2026) format and older flat formats.
    """
    all_messages: list[dict] = []

    for convo in conversations:
        title = convo.get("title", "Untitled")
        mapping = convo.get("mapping")

        if mapping and isinstance(mapping, dict):
            # Current format: tree structure with parent-chain traversal
            _extract_from_mapping(mapping, title, all_messages)
        elif "messages" in convo and isinstance(convo["messages"], list):
            # Older flat format (pre-2024)
            _extract_from_flat(convo["messages"], title, all_messages)

    return all_messages


def _extract_from_mapping(
    mapping: dict, title: str, out: list[dict]
) -> None:
    """Extract user messages from the tree-structured mapping format."""
    for node in mapping.values():
        message = node.get("message")
        if message is None:
            continue

        author = message.get("author", {})
        role = author.get("role", "")
        if role != "user":
            continue

        content = _extract_content(message)
        if not content:
            continue

        timestamp = _parse_timestamp(message.get("create_time"))
        word_count = len(content.split())

        out.append({
            "role": "user",
            "content": content,
            "timestamp": timestamp,
            "conversation_title": title,
            "word_count": word_count,
        })


def _extract_from_flat(
    messages: list[dict], title: str, out: list[dict]
) -> None:
    """Extract user messages from the older flat list format."""
    for message in messages:
        role = message.get("role", "")
        if role != "user":
            continue

        content = message.get("content", "")
        if isinstance(content, dict):
            # Some formats nest content in parts
            parts = content.get("parts", [])
            content = " ".join(str(p) for p in parts if isinstance(p, str))

        if not content or not content.strip():
            continue

        timestamp = _parse_timestamp(message.get("create_time"))
        word_count = len(content.split())

        out.append({
            "role": "user",
            "content": content,
            "timestamp": timestamp,
            "conversation_title": title,
            "word_count": word_count,
        })


def _extract_content(message: dict) -> str:
    """Pull text content from a message node, handling various content formats."""
    content = message.get("content", {})

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, dict):
        parts = content.get("parts", [])
        text_parts = []
        for part in parts:
            if isinstance(part, str):
                text_parts.append(part)
            elif isinstance(part, dict) and "text" in part:
                text_parts.append(part["text"])
        return " ".join(text_parts).strip()

    return ""


def _parse_timestamp(raw: float | str | None) -> str | None:
    """Convert a UNIX timestamp or ISO string to ISO format. Returns None if unparseable."""
    if raw is None:
        return None
    try:
        if isinstance(raw, (int, float)):
            return datetime.fromtimestamp(raw, tz=timezone.utc).isoformat()
        if isinstance(raw, str):
            return raw
    except (ValueError, OSError, OverflowError):
        return None
    return None
