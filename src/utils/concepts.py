"""Episode concept generation + parsing.

Moved out of app.py so the Story tab and any future UI can reuse it.
Includes the markdown-bold stripping fix (LLMs sometimes wrap parsed
fields in **bold**, which leaks into metadata and double-formats on render).
"""

import re
from typing import Dict, Any, List

# Canonical tone options — shared between the manual multiselect and the
# concept parser's whitelist. Keep in sync with the Story tab.
VALID_TONES = [
    "More battles and skirmishes",
    "Psychological horror",
    "Action-heavy combat",
    "Transformation focus",
    "Gravedancer origin elements",
    "Droid engagement focus",
    "Jedi POV chapters",
    "Traps and ambushes",
    "Honor and ritual",
    "Mystical / Force elements",
    "Political intrigue",
    "Survival horror",
    "Narrow escapes",
    "Ongoing pursuit (no kill)",
]

# Target novella length — kept here so concept + story prompts agree.
TARGET_WORDS = 7500


def get_used_jedi_names(episodes: List[Dict[str, Any]]) -> List[str]:
    """Collect Jedi names already used across the library (for dedup)."""
    names = []
    for ep in episodes:
        jedi_name = str(ep.get("target_jedi_name") or ep.get("jedi_name") or "").strip()
        if jedi_name and jedi_name.lower() != "unknown":
            names.append(jedi_name)
    return names


def _strip_markdown(value: str) -> str:
    """Remove markdown bold/italic markers and stray list bullets."""
    if not value:
        return ""
    # Drop **bold**, __bold__, *italic*, _italic_ wrappers and leading bullets.
    value = re.sub(r"\*{1,2}|_{1,2}", "", value)
    value = re.sub(r"^\s*[-*]\s+", "", value)
    return value.strip()


def build_full_episode_concept_prompt(used_names: List[str]) -> str:
    """Build prompt for generating a complete episode concept (all fields)."""
    exclusion = ""
    if used_names:
        exclusion = f"""

**ALREADY USED JEDI NAMES (DO NOT REPEAT OR CREATE SIMILAR VARIANTS):**
{', '.join(used_names)}

You must create a completely original name that is distinct from all of the above. Do not reuse any name, nickname, species name, or obvious variation."""

    return f"""Generate a complete original episode concept for "Gravedancer to General: Anatomy of a Catastrophe". Fill in every field below with creative, evocative, Star Wars-appropriate content.

This is a pre-Clone Wars era story. The protagonist is Qymaen jai Sheelal (the Gravedancer, evolving toward General Grievous) hunting an original Jedi. The story spans multiple days of pursuit, combat, traps, or psychological warfare.

**STORY LENGTH REQUIREMENT:** This is a self-contained novella. Target **~{TARGET_WORDS:,} words total** (range 6,500-9,000). The reader should be able to sit down for ~35-45 minutes and finish the complete story. Default to 5 days (~1,500 words/day) unless the concept calls for more or fewer.

**For the episode, provide:**

**Episode Title:** [Evocative, two-part Star Wars-style title, e.g., "The Hunting of Jedi Vex'arii", "Ash and Bone on Kalee", "The Gravedancer's Prey"]

**Number of Days:** [Default 5 unless the concept calls for more or fewer. 3 days = compact, intense. 5 days = standard novella pacing (recommended). 7 days = slower, more reflective. Pick what serves the concept best]

**Setting / Planet:** [Specific Star Wars location — Kalee, Jabiim, Florrum, Rattatak, Korriban, or another Outer Rim world. Be specific with terrain features that can sustain multi-day pursuit, ambush, and combat scenes]

**Jedi Name:** [Original alien-sounding name, distinct from Star Wars canon]{exclusion}

**Jedi Species:** [Non-human preferred — Miraluka, Twi'lek, Zabrak, Kel Dor, Nautolan, Cerean, Togruta, Weequay, Nikto, Devaronian, Chiss, Pantoran, etc.]

**Jedi Rank:** [Jedi Knight, Master, Padawan, or Consular]

**Lightsaber Color:** [Non-standard preferred — viridian, amber, silver, yellow, orange, cyan, white, magenta, or dual-bladed]

**Jedi Personality/Ability:** [1-2 sentences — distinctive personality trait, fighting style (Form I-VII or unorthodox), Force ability]

**Why Targeted:** [1 sentence — specific reason the Gravedancer hunts this Jedi. Could be strategic, revenge, or Sith-ordered]

**Tone / Focus (pick 2-4):** [From this list, pick 2-4 that fit: {", ".join(VALID_TONES)}]

**OUTPUT FORMAT (strict, use these exact headers, NO markdown bold):**

TITLE: [title]
DAYS: [number]
SETTING: [setting]
JEDI_NAME: [name]
JEDI_SPECIES: [species]
JEDI_RANK: [rank]
JEDI_SABER: [color]
JEDI_PERSONALITY: [personality]
JEDI_WHY_TARGETED: [reason]
TONE: [comma-separated list of 2-4 tone options]

Be creative. Make the setting and Jedi feel distinct from previous episodes. Ensure the title is evocative and Star Wars-appropriate. Plan the multi-day structure: day 1 sets up, middle days escalate through multiple short scenes per day, final day climaxes."""


def parse_full_episode_concept(response: str) -> Dict[str, Any]:
    """Parse LLM response into an episode concept dict.

    Strips markdown bold/italic from every value so metadata never carries
    stray ``**`` markers that double-format on render.
    """
    concept: Dict[str, Any] = {
        "title": "",
        "days": 5,
        "setting": "",
        "jedi_name": "",
        "jedi_species": "",
        "jedi_rank": "",
        "jedi_saber": "",
        "jedi_personality": "",
        "jedi_target": "",
        "tone": [],
    }

    field_patterns = {
        "title": r"TITLE:\s*(.*?)(?=\n[A-Z_]+:|\Z)",
        "days": r"DAYS:\s*(\d+)",
        "setting": r"SETTING:\s*(.*?)(?=\n[A-Z_]+:|\Z)",
        "jedi_name": r"JEDI_NAME:\s*(.*?)(?=\n[A-Z_]+:|\Z)",
        "jedi_species": r"JEDI_SPECIES:\s*(.*?)(?=\n[A-Z_]+:|\Z)",
        "jedi_rank": r"JEDI_RANK:\s*(.*?)(?=\n[A-Z_]+:|\Z)",
        "jedi_saber": r"JEDI_SABER:\s*(.*?)(?=\n[A-Z_]+:|\Z)",
        "jedi_personality": r"JEDI_PERSONALITY:\s*(.*?)(?=\n[A-Z_]+:|\Z)",
        "jedi_target": r"JEDI_WHY_TARGETED:\s*(.*?)(?=\n[A-Z_]+:|\Z)",
        "tone": r"TONE:\s*(.*?)(?=\n[A-Z_]+:|\Z)",
    }

    for key, pattern in field_patterns.items():
        match = re.search(pattern, response, re.DOTALL)
        if not match:
            continue
        value = match.group(1).strip()
        if key == "days":
            try:
                concept["days"] = max(3, min(8, int(value)))
            except ValueError:
                concept["days"] = 5
        elif key == "tone":
            tones = [t.strip() for t in value.split(",")]
            # Strip markdown + filter to the whitelist so junk doesn't sneak in.
            tones = [_strip_markdown(t) for t in tones]
            concept["tone"] = [t for t in tones if t in VALID_TONES]
        else:
            concept[key] = _strip_markdown(value)

    return concept
