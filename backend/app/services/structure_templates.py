"""Story structure templates.

System recommends based on genre; user can accept or override.
Each template provides a beat-level framework for outlining a novel.
"""

STRUCTURE_TEMPLATES: dict[str, dict] = {
    "save_the_cat_15": {
        "name": "Save the Cat (15 beats)",
        "description": "The most popular commercial fiction framework. 15 beats with percentage-based placement.",
        "genres": ["romance", "thriller", "mystery", "fantasy"],
        "beats": [
            {"position": 1, "name": "Opening Image", "pct": 0, "description": "The 'before' snapshot. Show the protagonist's world as it is."},
            {"position": 2, "name": "Theme Stated", "pct": 5, "description": "Someone states the lesson the protagonist will learn — they don't understand it yet."},
            {"position": 3, "name": "Setup", "pct": 10, "description": "Establish the protagonist's world, relationships, and what's at stake."},
            {"position": 4, "name": "Catalyst", "pct": 10, "description": "The event that disrupts the status quo. The story begins here."},
            {"position": 5, "name": "Debate", "pct": 15, "description": "The protagonist resists the call. Should they act? What will it cost?"},
            {"position": 6, "name": "Break into Two", "pct": 20, "description": "The protagonist commits. They leave the old world behind."},
            {"position": 7, "name": "B Story", "pct": 22, "description": "The subplot begins — often a relationship that teaches the theme."},
            {"position": 8, "name": "Fun and Games", "pct": 30, "description": "The promise of the premise. What the reader came to see."},
            {"position": 9, "name": "Midpoint", "pct": 50, "description": "False victory or false defeat. Stakes escalate. No going back."},
            {"position": 10, "name": "Bad Guys Close In", "pct": 55, "description": "External pressure mounts. Internal doubts grow. Allies fracture."},
            {"position": 11, "name": "All Is Lost", "pct": 75, "description": "The lowest point. Something or someone is lost. A 'death' — literal or metaphorical."},
            {"position": 12, "name": "Dark Night of the Soul", "pct": 80, "description": "The protagonist faces despair. What's the point? Why keep going?"},
            {"position": 13, "name": "Break into Three", "pct": 80, "description": "The aha moment. The theme clicks. The protagonist knows what to do."},
            {"position": 14, "name": "Finale", "pct": 85, "description": "The protagonist acts on what they've learned. Confrontation. Resolution."},
            {"position": 15, "name": "Final Image", "pct": 100, "description": "The 'after' snapshot. Mirror of the opening — but everything has changed."},
        ],
    },
    "romancing_the_beat_20": {
        "name": "Romancing the Beat (20 beats)",
        "description": "The standard romance framework. Four phases, twenty beats centered on the relationship arc.",
        "genres": ["romance"],
        "beats": [
            {"position": 1, "name": "Setup (Character A)", "pct": 0, "description": "Introduce Character A in their normal world. What's missing emotionally?"},
            {"position": 2, "name": "Setup (Character B)", "pct": 3, "description": "Introduce Character B in their normal world. What's missing emotionally?"},
            {"position": 3, "name": "Meet", "pct": 8, "description": "The meet-cute or first encounter. First impressions — attraction AND friction."},
            {"position": 4, "name": "Denial", "pct": 12, "description": "Both resist the attraction. It's inconvenient, inappropriate, or terrifying."},
            {"position": 5, "name": "No Way", "pct": 15, "description": "External or internal obstacles reinforce why this relationship can't work."},
            {"position": 6, "name": "Forced Proximity", "pct": 20, "description": "Circumstances force them together despite resistance."},
            {"position": 7, "name": "Vulnerability", "pct": 25, "description": "First genuine emotional moment. A crack in the armor."},
            {"position": 8, "name": "Deepening", "pct": 30, "description": "Getting to know each other. Shared experiences build genuine connection."},
            {"position": 9, "name": "Inkling", "pct": 35, "description": "One or both begin to realize feelings are real — and that's scary."},
            {"position": 10, "name": "Midpoint: Commitment", "pct": 50, "description": "A choice to be together — physical, emotional, or both. The relationship is real now."},
            {"position": 11, "name": "Deepening 2", "pct": 55, "description": "The relationship grows. But the core wound hasn't been addressed yet."},
            {"position": 12, "name": "Retreat", "pct": 60, "description": "The weight of vulnerability becomes too much. One or both pull back."},
            {"position": 13, "name": "External Complication", "pct": 65, "description": "An outside force threatens the relationship."},
            {"position": 14, "name": "Crisis", "pct": 70, "description": "The core wound surfaces. The very thing they fear most is happening."},
            {"position": 15, "name": "Dark Moment", "pct": 75, "description": "The breakup. All seems lost. Each is alone again — but changed."},
            {"position": 16, "name": "Realization", "pct": 80, "description": "Alone, each confronts what they really want. Growth happens."},
            {"position": 17, "name": "Grand Gesture", "pct": 85, "description": "One (or both) takes a bold action to win the other back."},
            {"position": 18, "name": "Reunion", "pct": 90, "description": "They come back together. The wound is acknowledged and healed."},
            {"position": 19, "name": "Climax", "pct": 95, "description": "Final obstacle overcome together. They choose each other fully."},
            {"position": 20, "name": "HEA/HFN", "pct": 100, "description": "Happily Ever After or Happy For Now. The new normal — together."},
        ],
    },
    "seven_point": {
        "name": "Seven-Point Structure",
        "description": "Milestone-driven, flexible between plotted points. Popular for fantasy and sci-fi.",
        "genres": ["fantasy", "scifi", "litrpg"],
        "beats": [
            {"position": 1, "name": "Hook", "pct": 0, "description": "The starting state — opposite of the resolution. Draw the reader in."},
            {"position": 2, "name": "Plot Turn 1", "pct": 15, "description": "The event that sets the story in motion. The protagonist enters a new world or situation."},
            {"position": 3, "name": "Pinch Point 1", "pct": 30, "description": "Pressure from the antagonist. Show the stakes. Force the protagonist to act."},
            {"position": 4, "name": "Midpoint", "pct": 50, "description": "The protagonist shifts from reactive to proactive. They commit."},
            {"position": 5, "name": "Pinch Point 2", "pct": 65, "description": "Maximum pressure. The plan fails. Allies fall. Resources depleted."},
            {"position": 6, "name": "Plot Turn 2", "pct": 80, "description": "The final piece falls into place. The protagonist has what they need."},
            {"position": 7, "name": "Resolution", "pct": 100, "description": "Climax and resolution. Opposite of the hook — everything has changed."},
        ],
    },
    "three_act_24": {
        "name": "Three-Act Structure (24 chapters)",
        "description": "Classic three-act with 24-chapter breakdown. Versatile for all genres.",
        "genres": ["thriller", "mystery", "fantasy", "scifi", "romance"],
        "beats": [
            {"position": 1, "name": "Act 1: Setup", "pct": 0, "description": "Chapters 1-6. Establish world, characters, stakes."},
            {"position": 2, "name": "Inciting Incident", "pct": 10, "description": "Chapter 2-3. The event that disrupts the status quo."},
            {"position": 3, "name": "First Act Turn", "pct": 25, "description": "Chapter 6. The protagonist commits to the journey."},
            {"position": 4, "name": "Act 2A: Rising Action", "pct": 25, "description": "Chapters 7-12. Protagonist pursues goal, meets obstacles."},
            {"position": 5, "name": "Midpoint Reversal", "pct": 50, "description": "Chapter 12. Everything changes. False victory or devastating defeat."},
            {"position": 6, "name": "Act 2B: Complications", "pct": 50, "description": "Chapters 13-18. Stakes escalate. Allies tested. Plans fail."},
            {"position": 7, "name": "Second Act Turn / All Is Lost", "pct": 75, "description": "Chapter 18. Lowest point. Protagonist must face their deepest fear."},
            {"position": 8, "name": "Act 3: Climax", "pct": 75, "description": "Chapters 19-24. Confrontation, resolution, new equilibrium."},
        ],
    },
    "progression_ladder": {
        "name": "Progression Ladder",
        "description": "Level-up milestones for LitRPG/Progression Fantasy. Power scaling with narrative stakes.",
        "genres": ["litrpg"],
        "beats": [
            {"position": 1, "name": "System Introduction", "pct": 0, "description": "Chapter 1. The system/power framework is revealed to the protagonist."},
            {"position": 2, "name": "First Power-Up", "pct": 8, "description": "Early win. Protagonist gains first ability. Reader sees the progression loop."},
            {"position": 3, "name": "Training Arc", "pct": 15, "description": "Learning the system. Costs and limitations established."},
            {"position": 4, "name": "First Real Challenge", "pct": 25, "description": "Current power level tested. Protagonist barely wins or fails."},
            {"position": 5, "name": "Tier Break 1", "pct": 35, "description": "Major power milestone. New abilities unlocked. New dangers accessible."},
            {"position": 6, "name": "Mid-Tier Plateau", "pct": 50, "description": "Power growth slows. Protagonist must innovate, not just level up."},
            {"position": 7, "name": "Tier Break 2", "pct": 65, "description": "Second major milestone. The cost of power becomes personal."},
            {"position": 8, "name": "Power Cost Reveal", "pct": 75, "description": "The system has a hidden cost or limitation that threatens everything."},
            {"position": 9, "name": "Climactic Application", "pct": 90, "description": "Protagonist uses accumulated abilities in a creative final confrontation."},
            {"position": 10, "name": "New Horizon", "pct": 100, "description": "Victory — but a higher tier is revealed. Series hook."},
        ],
    },
}


def get_recommended_structure(genre: str | None, distribution_format: str | None = None) -> str:
    """Recommend a structure template based on genre and format."""
    if not genre:
        return "save_the_cat_15"

    genre_lower = genre.lower()

    if "romance" in genre_lower:
        return "romancing_the_beat_20"
    elif "litrpg" in genre_lower or "progression" in genre_lower:
        return "progression_ladder"
    elif genre_lower in ("fantasy", "scifi", "sci-fi", "science fiction"):
        return "seven_point"
    elif genre_lower in ("thriller", "mystery"):
        return "save_the_cat_15"
    else:
        return "three_act_24"


def get_all_templates() -> dict:
    """Return all templates for the user to browse."""
    return {
        key: {
            "name": val["name"],
            "description": val["description"],
            "beat_count": len(val["beats"]),
        }
        for key, val in STRUCTURE_TEMPLATES.items()
    }
