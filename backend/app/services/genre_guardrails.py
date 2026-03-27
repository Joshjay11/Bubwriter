"""Genre and format guardrails for the Brain stage.

These inject structural constraints into scene planning.
Not a database table — system defaults that ship with the product.
"""

GENRE_GUARDRAILS: dict[str, dict] = {
    "romance": {
        "mandatory_beats": [
            "meet-cute or first encounter",
            "first conflict or misunderstanding",
            "growing attraction despite obstacles",
            "dark moment / all-is-lost",
            "grand gesture or reconciliation",
            "HEA (Happily Ever After) or HFN (Happy For Now)",
        ],
        "trope_awareness": True,
        "pov_rules": "Dual POV is standard. Each POV chapter should deepen the reader's understanding of why these two people belong together.",
        "pacing_note": "Romance readers expect emotional escalation every chapter. Never go more than 2 chapters without advancing the relationship.",
    },
    "thriller": {
        "mandatory_beats": [
            "inciting incident within first 10%",
            "midpoint reversal at ~50%",
            "darkest moment at ~75%",
            "climax and resolution",
        ],
        "clue_tracking": True,
        "pov_rules": "Antagonist POV scenes should reveal just enough to create dramatic irony without spoiling the mystery.",
        "pacing_note": "Chapter-end hooks are mandatory. Every chapter must end on a question, revelation, or cliffhanger.",
    },
    "fantasy": {
        "mandatory_beats": [
            "world introduction within first 5%",
            "call to adventure or disruption of status quo",
            "midpoint escalation",
            "dark night of the soul",
            "climactic confrontation",
        ],
        "worldbuilding_enforcement": True,
        "pov_rules": "If using multiple POVs, each POV character must have a distinct voice and their own subplot arc.",
        "pacing_note": "Balance worldbuilding exposition with action. Never info-dump for more than one paragraph without interruption.",
    },
    "scifi": {
        "mandatory_beats": [
            "establish the world's key difference from ours",
            "inciting incident",
            "midpoint revelation about the world or technology",
            "climax that leverages the sci-fi premise",
        ],
        "worldbuilding_enforcement": True,
        "pov_rules": "Technology should feel lived-in, not explained. Characters interact with tech the way we interact with smartphones — without marveling at them.",
        "pacing_note": "Hard sci-fi readers tolerate longer exposition. Space opera readers expect faster pacing. Match the subgenre.",
    },
    "litrpg": {
        "mandatory_beats": [
            "system introduction within first chapter",
            "first power-up or level gain",
            "major ability milestone at midpoint",
            "power cost or limitation reveal",
            "climactic use of accumulated abilities",
        ],
        "progression_tracking": True,
        "pov_rules": "Stat screens and system notifications should be brief and integrated into the narrative, not walls of text.",
        "pacing_note": "Readers expect measurable progress every 2-3 chapters. Track power scaling to prevent both stagnation and power creep.",
    },
    "mystery": {
        "mandatory_beats": [
            "crime or puzzle introduced in first chapter",
            "first false lead by 25%",
            "midpoint revelation that reframes the case",
            "second false lead or complication at 60%",
            "final clue and confrontation",
        ],
        "clue_tracking": True,
        "pov_rules": "Fair-play rule: every clue the detective uses in the solution must appear on-page before the reveal.",
        "pacing_note": "Plant at least one clue or red herring per chapter. The reader should be able to solve it if they're paying attention.",
    },
}

FORMAT_GUARDRAILS: dict[str, dict] = {
    "kindle_ebook": {
        "chapter_length": "2,000-3,000 words",
        "structure_rule": "Every chapter must end on a hook — question, revelation, or cliffhanger. KU readers abandon quickly.",
        "key_metric": "Completion rate drives page-read revenue. Optimize first 10% aggressively.",
        "beat_placement": "Major cliffhangers at 25%, 50%, and 75% marks to prevent Act 2 sag.",
    },
    "kindle_unlimited": {
        "chapter_length": "2,000-3,000 words",
        "structure_rule": "Binge-pacing: shorter chapters with aggressive hooks. Readers consume in 1-2 sittings.",
        "key_metric": "Page-reads = revenue. Completion rate is everything.",
        "beat_placement": "Major cliffhangers at 25%, 50%, and 75% marks.",
    },
    "web_serial": {
        "chapter_length": "1,500-3,500 words per update",
        "structure_rule": "Nested 10-chapter micro-arcs. Each arc has its own inciting incident and climax. End every update on a hook.",
        "key_metric": "Consistent posting schedule matters more than chapter length. Missing updates kills visibility.",
        "beat_placement": "Deliver a 'Premise Promise' payoff by chapter 3. Mini-climax every 10 chapters.",
    },
    "audiobook": {
        "chapter_length": "Shorter chapters (~2,000 words) as natural stopping points",
        "structure_rule": "Optimize for listenability. Avoid visual-only formatting. Ensure character voices are distinct enough for audio differentiation.",
        "key_metric": "Listening clarity. Avoid similar-sounding character names. Flag monologues over 2 minutes.",
        "beat_placement": "Scene transitions should be signaled clearly — listeners can't scan back easily.",
    },
    "trade_paperback": {
        "chapter_length": "2,500-5,000 words",
        "structure_rule": "Standard three-act structure. More room for literary prose and longer scenes.",
        "key_metric": "Reader satisfaction and reviews. Less pressure on aggressive hooks.",
        "beat_placement": "Standard act breaks at 25%, 50%, 75%.",
    },
}


def build_genre_guardrails(genre: str | None, distribution_format: str | None) -> str:
    """Build a prompt block with genre and format constraints for the Brain stage."""
    parts: list[str] = []

    if genre and genre.lower() in GENRE_GUARDRAILS:
        g = GENRE_GUARDRAILS[genre.lower()]
        parts.append("GENRE CONSTRAINTS:")
        parts.append(f"Genre: {genre.title()}")
        if g.get("mandatory_beats"):
            beats = ", ".join(g["mandatory_beats"])
            parts.append(f"Mandatory story beats: {beats}")
        if g.get("pov_rules"):
            parts.append(f"POV guidance: {g['pov_rules']}")
        if g.get("pacing_note"):
            parts.append(f"Pacing: {g['pacing_note']}")

    if distribution_format and distribution_format.lower() in FORMAT_GUARDRAILS:
        f = FORMAT_GUARDRAILS[distribution_format.lower()]
        parts.append("\nFORMAT CONSTRAINTS:")
        parts.append(f"Distribution: {distribution_format.replace('_', ' ').title()}")
        parts.append(f"Target chapter length: {f['chapter_length']}")
        parts.append(f"Structure: {f['structure_rule']}")
        parts.append(f"Key metric: {f['key_metric']}")
        if f.get("beat_placement"):
            parts.append(f"Beat placement: {f['beat_placement']}")

    return "\n".join(parts) if parts else ""
