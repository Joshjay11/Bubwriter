"""Conversation message filter — selects personality-rich messages for analysis.

Three-stage pipeline:
  A. Mechanical filters (word count, code detection, deduplication)
  B. Qualitative filter (LLM-based personality/voice signal detection)
  C. Cap at 500 messages (take longest if over limit)

Privacy: no message content is logged — only counts and statistics.
"""

import json
import logging
import re

from app.services import llm_service

logger = logging.getLogger(__name__)

# --- Stage A constants ---
MIN_WORD_COUNT = 30
CODE_FENCE_RE = re.compile(r"```[\s\S]*?```")
MAX_MESSAGES_AFTER_FILTER = 500
LLM_BATCH_SIZE = 50

# Prompt for the qualitative filter LLM call
_FILTER_SYSTEM = """You are a message classifier. You will receive a numbered \
list of messages written by a person in their AI conversations. Your job is to \
identify which messages reveal personality, communication style, opinions, \
emotions, or creative expression.

INCLUDE messages that contain: opinions, emotional language, descriptive \
language, storytelling, personal anecdotes, arguments, explanations of \
beliefs or values, humor, frustration, enthusiasm, or self-reflection.

EXCLUDE messages that are: purely transactional ("fix this", "make it shorter"), \
simple acknowledgments ("thanks", "ok got it"), bare instructions with no \
personality signal, or purely technical/code-focused.

Return ONLY a JSON array of the message numbers that should be INCLUDED.
Example: [1, 3, 5, 8]

If none qualify, return an empty array: []"""


async def filter_messages(messages: list[dict]) -> list[dict]:
    """Filter a list of user messages to keep only personality-rich content.

    Args:
        messages: List of message dicts from conversation_parser, each with
                  'content', 'word_count', and other metadata fields.

    Returns:
        Filtered list of message dicts (max 500), ordered by word count
        descending when capping is needed.
    """
    total_input = len(messages)
    logger.info("Filter input: %d messages", total_input)

    # Stage A: mechanical filters
    after_mechanical = _apply_mechanical_filters(messages)
    logger.info(
        "After mechanical filters: %d messages (from %d)",
        len(after_mechanical),
        total_input,
    )

    if len(after_mechanical) == 0:
        return []

    # Stage B: qualitative LLM filter
    after_qualitative = await _apply_qualitative_filter(after_mechanical)
    logger.info(
        "After qualitative filter: %d messages (from %d)",
        len(after_qualitative),
        len(after_mechanical),
    )

    # Stage C: cap at 500 (take longest)
    if len(after_qualitative) > MAX_MESSAGES_AFTER_FILTER:
        after_qualitative.sort(key=lambda m: m["word_count"], reverse=True)
        after_qualitative = after_qualitative[:MAX_MESSAGES_AFTER_FILTER]
        logger.info("Capped to %d messages", MAX_MESSAGES_AFTER_FILTER)

    return after_qualitative


def _apply_mechanical_filters(messages: list[dict]) -> list[dict]:
    """Drop short, code-heavy, and duplicate messages."""
    seen_normalized: set[str] = set()
    result: list[dict] = []

    for msg in messages:
        content = msg["content"]
        word_count = msg["word_count"]

        # Filter: minimum word count
        if word_count < MIN_WORD_COUNT:
            continue

        # Filter: >50% code content
        if _is_mostly_code(content):
            continue

        # Filter: near-duplicate detection (normalize whitespace + lowercase)
        normalized = re.sub(r"\s+", " ", content.strip().lower())
        # Use first 200 chars as fingerprint to catch near-dupes
        fingerprint = normalized[:200]
        if fingerprint in seen_normalized:
            continue
        seen_normalized.add(fingerprint)

        result.append(msg)

    return result


def _is_mostly_code(content: str) -> bool:
    """Check if more than 50% of the message content is inside code fences."""
    code_blocks = CODE_FENCE_RE.findall(content)
    if not code_blocks:
        return False
    code_char_count = sum(len(block) for block in code_blocks)
    return code_char_count > (len(content) * 0.5)


async def _apply_qualitative_filter(messages: list[dict]) -> list[dict]:
    """Use LLM to identify messages with personality/voice signal.

    Processes messages in batches of 50 to keep prompt sizes manageable.
    Falls back to keeping all messages if the LLM call fails.
    """
    selected_indices: set[int] = set()

    for batch_start in range(0, len(messages), LLM_BATCH_SIZE):
        batch = messages[batch_start : batch_start + LLM_BATCH_SIZE]

        # Build numbered list for the LLM
        numbered_lines = []
        for i, msg in enumerate(batch):
            # Truncate very long messages to first 200 words for the filter prompt
            words = msg["content"].split()
            preview = " ".join(words[:200])
            if len(words) > 200:
                preview += "..."
            numbered_lines.append(f"{i + 1}. {preview}")

        user_prompt = "\n\n".join(numbered_lines)

        try:
            raw_response = await llm_service.generate(
                system_prompt=_FILTER_SYSTEM,
                user_prompt=user_prompt,
                temperature=0.3,
                max_tokens=1000,
            )
            # Parse the JSON array of indices
            indices = _parse_index_array(raw_response, len(batch))
            for idx in indices:
                # Convert 1-based LLM index to 0-based global index
                selected_indices.add(batch_start + idx - 1)
        except Exception:
            logger.warning(
                "Qualitative filter LLM call failed for batch at %d, "
                "keeping all %d messages in batch",
                batch_start,
                len(batch),
            )
            # Fallback: keep all messages in this batch
            for i in range(len(batch)):
                selected_indices.add(batch_start + i)

    return [messages[i] for i in sorted(selected_indices) if i < len(messages)]


def _parse_index_array(raw: str, batch_size: int) -> list[int]:
    """Parse LLM response as a JSON array of 1-based message indices.

    Handles markdown-wrapped JSON and validates index bounds.
    """
    cleaned = raw.strip()
    # Strip markdown fencing if present
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    indices = json.loads(cleaned)
    if not isinstance(indices, list):
        return []

    # Validate: keep only valid 1-based indices within batch bounds
    return [
        int(idx) for idx in indices
        if isinstance(idx, (int, float)) and 1 <= int(idx) <= batch_size
    ]
