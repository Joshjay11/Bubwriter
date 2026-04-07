"""Post-generation anti-slop validation.

Runs AFTER Voice model output, BEFORE returning to user.
Catches what the prompt-based system misses (~30-40% of AI tells).
Returns a slop score — doesn't auto-reject.
"""

import re
import statistics
from typing import Any


class SlopValidator:
    """Scans generated prose for banned words, AI-tell patterns, and cadence regularity."""

    # Universal slop patterns (always checked)
    UNIVERSAL_PATTERNS: list[tuple[str, str]] = [
        (r'\b(tapestry|testament|ministrations|visceral|palpable)\b', 'banned_word'),
        (r'\b(delve|delved|delving)\b', 'banned_word'),
        (r'\b(utiliz(?:e|ed|ing|ation))\b', 'banned_word'),
        (r'\b(myriad|plethora|meld|melded)\b', 'banned_word'),
        (r'\b(whilst|amongst|amidst)\b', 'banned_word'),
        (r'No \w+\.\s*No \w+\.\s*Just \w+\.', 'no_x_no_y_just_z'),
        (r"(?:It|That|This) was(?:n't)? (?:just|merely|simply)", 'weak_intensifier'),
        (r'A (?:symphony|dance|tapestry|testament|mosaic) of', 'purple_metaphor'),
        (r'(?:his|her|their) (?:heart|breath|pulse) (?:quickened|raced|hammered|pounded)', 'body_cliche'),
        (r'(?:eyes|gaze) (?:bore|bored|boring) into', 'gaze_cliche'),
    ]

    def validate(self, text: str, voice_profile: dict) -> dict[str, Any]:
        """Validate prose for slop patterns. Returns result with violations found."""
        violations: list[dict[str, Any]] = []

        # Check universal patterns
        for pattern, violation_type in self.UNIVERSAL_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                violations.append({
                    "type": violation_type,
                    "matches": matches[:5],
                    "count": len(matches),
                })

        # Check profile-specific banned words
        profile_bans = voice_profile.get("anti_slop", {}).get("personal_banned_words", [])
        for word in profile_bans:
            found = re.findall(rf'\b{re.escape(word)}\b', text, re.IGNORECASE)
            if found:
                violations.append({
                    "type": "profile_banned_word",
                    "matches": [word],
                    "count": len(found),
                })

        # Cadence regularity check — AI prose tends toward uniform sentence length
        sentences = [s.strip() for s in re.split(r'[.!?]+', text) if s.strip()]
        lengths = [len(s.split()) for s in sentences]
        if len(lengths) > 3:
            std_dev = statistics.stdev(lengths)
            if std_dev < 3.0:
                violations.append({
                    "type": "cadence_too_regular",
                    "matches": [f"std_dev={std_dev:.1f} (threshold: 3.0)"],
                    "count": 1,
                })

        word_count = len(text.split())
        slop_score = round(len(violations) / max(word_count / 100, 1), 2)

        return {
            "passed": len(violations) == 0,
            "violation_count": len(violations),
            "violations": violations,
            "slop_score": slop_score,
            "word_count": word_count,
        }


# Singleton
slop_validator = SlopValidator()
