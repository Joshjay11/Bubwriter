"""Anti-slop constraint system for the Voice generation stage.

Global banned words/phrases are the product's baseline quality floor.
Voice-specific rules from the user's profile layer on top.

ADDITIVE ONLY — you may add new banned words/phrases. Never remove
existing entries without Jayson's explicit approval.
"""

# --- Global Banned Words ---
# Common AI-sounding words that make prose feel generated.

GLOBAL_BANNED_WORDS: list[str] = [
    "delve",
    "tapestry",
    "testament",
    "beacon",
    "unwavering",
    "undeniable",
    "multifaceted",
    "commendable",
    "groundbreaking",
    "pivotal",
    "nuanced",
    "intricate",
    "paramount",
    "meticulous",
    "endeavor",
    "uncharted",
    "bustling",
    "dappled",
    "gossamer",
    "ethereal",
    "resplendent",
    "luminous",
    "labyrinthine",
    "ineffable",
    "palpable",
    "visceral",
    "tangible",
    "kaleidoscope",
    "cacophony",
    "symphony",
    "crucible",
    "maelstrom",
    "enigmatic",
    "inexorable",
    "juxtaposition",
]

# --- Global Banned Phrases ---
# AI-sounding phrase patterns that betray machine generation.

GLOBAL_BANNED_PHRASES: list[str] = [
    "a testament to",
    "it's worth noting that",
    "it's important to note",
    "a tapestry of",
    "in the tapestry of",
    "sends shivers down",
    "a dance of",
    "the weight of the world",
    "a symphony of",
    "a kaleidoscope of",
    "the silence was deafening",
    "hung in the air",
    "thick with tension",
    "time seemed to slow",
    "electricity crackled between",
    "a single tear rolled down",
    "let out a breath .* didn't know .* holding",
    "pierced the silence",
    "shattered the stillness",
    "the air crackled with",
    "eyes that held",
    "a world of",
    "their eyes met across",
    "a chill ran down",
]

# --- Global Structural Rules ---
# Patterns and tendencies that make AI prose feel formulaic.

GLOBAL_STRUCTURAL_RULES: list[str] = [
    "Do not start three consecutive paragraphs with the same word.",
    "Do not end a scene with a character smiling, sighing, or staring into the distance.",
    "Avoid 'As if' simile constructions more than once per scene.",
    "Do not use em-dashes more than three times per 1000 words.",
    "Do not use semicolons in dialogue.",
    "Avoid participial phrase openings ('Walking to the door, she...') more than twice per scene.",
    "Do not describe eyes as 'pools of' anything.",
    "Avoid the construction 'little did [character] know' entirely.",
    "Do not use 'couldn't help but' — just have the character do the thing.",
    "Avoid 'felt a surge of [emotion]' — show the emotion through action or thought instead.",
]


def build_anti_slop_block(voice_anti_slop: dict | None) -> str:
    """Build the anti-slop constraint block for the Voice/Polish prompt.

    Layers global defaults with voice-specific rules from the user's profile.
    Placed at BEGINNING of prompt (and referenced at END) to exploit
    the "Lost in the Middle" effect — models pay most attention to
    start and end of context.
    """
    if voice_anti_slop is None:
        voice_anti_slop = {}

    lines = ["--- ANTI-SLOP CONSTRAINTS (MANDATORY) ---"]

    # Layer 1: Global banned words
    lines.append("NEVER use these words: " + ", ".join(GLOBAL_BANNED_WORDS))

    # Layer 2: Global banned phrases
    lines.append("NEVER use these phrases: " + ", ".join(GLOBAL_BANNED_PHRASES))

    # Layer 3: Global structural rules
    for rule in GLOBAL_STRUCTURAL_RULES:
        lines.append(f"- {rule}")

    # Layer 4: Voice-specific rules (from user's profile)
    personal_words = voice_anti_slop.get("personal_banned_words", [])
    if personal_words:
        lines.append("ALSO NEVER use: " + ", ".join(personal_words))

    personal_patterns = voice_anti_slop.get("personal_banned_patterns", [])
    if personal_patterns:
        lines.append("ALSO NEVER use patterns: " + ", ".join(personal_patterns))

    cringe = voice_anti_slop.get("cringe_triggers", [])
    if cringe:
        lines.append("CRINGE TRIGGERS to avoid: " + ", ".join(cringe))

    genre_rules = voice_anti_slop.get("genre_constraints", [])
    if genre_rules:
        for rule in genre_rules:
            lines.append(f"- {rule}")

    lines.append("--- END ANTI-SLOP ---")
    return "\n".join(lines)
