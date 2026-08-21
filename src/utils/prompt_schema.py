"""Shared prompt schema fragments for story and concept generation.

Keeping the canonical wording here reduces drift between docs, UI labels,
tests, and the generation pipeline.
"""

from __future__ import annotations

import os
import re
from typing import Any


def _daily_target_tokens() -> int:
    """Read the daily token budget, tolerating a malformed env override."""
    try:
        return int(os.environ.get("GRAVEDANCER_DAILY_TARGET_TOKENS", "45000"))
    except (TypeError, ValueError):
        return 45000


# Shared constants
DAILY_TARGET_TOKENS = max(8_000, _daily_target_tokens())
TOKENS_PER_WORD_ESTIMATE = 1.3
TARGET_WORDS_PER_DAY = round(DAILY_TARGET_TOKENS / TOKENS_PER_WORD_ESTIMATE)
CHAPTERS_PER_DAY = 10
MIN_CHAPTERS_PER_DAY = 5
CONCEPT_MIN_DAYS = 3
CONCEPT_MAX_DAYS = 8

STORY_TONE_LINE = "**TONE / FOCUS:** {tone}"
STORY_EPISODE_HEADER = 'Write an episode for "Gravedancer to General: Anatomy of a Catastrophe".'
STORY_EPISODE_ARC_HEADER = "## EPISODE ARC"
STORY_OUTLINE_HEADER = 'Plan a {num_days}-day episode for "Gravedancer to General: Anatomy of a Catastrophe".'
STORY_SECTION_EXPANSION_HEADER = "Expand Section {section_index} of Day {day_number} into prose."
STORY_DAY_HEADING = "## DAY {day_number}: [Descriptive Title]"

# Story prompt fragments
STORY_BASE_CONSTRAINTS = [
    "Write a complete {num_days}-day novella following the series format.",
    f"Target ~{TARGET_WORDS_PER_DAY:,} words per day.",
    "Each day should have 5 distinct chapters.",
    "Each chapter should contain 4 concise, concrete beats.",
]

STORY_MULTI_PASS_RULES = [
    "Treat this as a structured planning task first and a prose task second:",
    "1. Establish the episode arc and thematic spine.",
    "2. Keep each day internally coherent with its own escalation and hook.",
    "3. Preserve continuity of injuries, locations, emotional state, and tactics.",
    "4. Expand only the micro-beats already implied by the setup instead of inventing new major turns.",
    "5. Keep the story moving forward at every paragraph.",
    "6. Use the current expansion level only: when outlining, outline; when drafting a day, write the day; when drafting a section, stay inside that section.",
]

STORY_STRUCTURE_REQUIREMENTS = [
    "Clear narrative arc (setup → rising action → climax → resolution/open ending)",
    "Protagonist transformation arc: Qymaen ends the episode further along the path to Grievous — colder, more cybernetic, more willing to cross lines",
    "A thematic spine (one core theme per episode: cost of honor, seduction of power, war as ritual, what makes a monster, the last human thing)",
    "A distinct Jedi antagonist with their own philosophy and a defining moment of choice",
    "A closing image that lands like a hammer — a single image, decision, or haunting line on the final day",
    "The Jedi's fate must follow the approved concept; death, escape, or a continuing pursuit are all valid when supported by the episode arc",
]

STORY_DEEPENING_REQUIREMENTS = [
    "Sensory immersion: weather, light, sound, smell, taste, texture, temperature in every scene",
    "Character interiority: Qymaen's thoughts, doubts, memories of Ronderu lij Kummar, the whisper of his augmentations, the weight of his mask",
    "Tactical detail: how combat actually unfolds — footwork, breathing, the hiss of servos, the angle of a parry, the choice of terrain",
    "Worldbuilding texture: cultural rituals, alien flora/fauna, droid chatter, the politics of supply lines",
    "Sub-scene structure: each day should have 5 distinct chapters with room for atmosphere, tactics, reversals, and consequences",
    "Nested beat structure: each chapter should contain 4 concise concrete beats",
    "Dialogue: sparse but earned — every line should reveal character or advance tension",
    "Cliffhangers/hooks: each day ends on a hook or revelation that pulls the reader forward",
]

STORY_PACING_RULES = [
    "Day 1: Arrival, recon, first contact. Set atmosphere, introduce the Jedi (from a distance), establish stakes, plant thematic seed.",
    "Middle days: Escalation, traps, skirmishes, psychological warfare. Sub-plot beats. Character revelations. The Jedi becomes real.",
    "Final day: The Jedi dies — the confrontation the entire episode has been building toward, ending in the Jedi's death unless the tone is 'Ongoing pursuit (no kill)'. Combat OR pursuit OR transformation moment. End on a closing image.",
]


# Concept helpers


def build_story_word_budget(num_days: int) -> int:
    return TARGET_WORDS_PER_DAY


# Story helpers
def build_story_constraints_block(num_days: int) -> str:
    return "\n".join(item.format(num_days=num_days) for item in STORY_BASE_CONSTRAINTS)


def build_story_multi_pass_block() -> str:
    return "\n".join(STORY_MULTI_PASS_RULES)


def build_story_structure_block() -> str:
    return "\n".join(f"- {item}" for item in STORY_STRUCTURE_REQUIREMENTS)


def build_story_deepening_block() -> str:
    return "\n".join(f"- {item}" for item in STORY_DEEPENING_REQUIREMENTS)


def build_story_pacing_block() -> str:
    return "\n".join(f"- {item}" for item in STORY_PACING_RULES)


# Validation helpers
def validate_concept_dict(concept: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    if not concept.get("title"):
        errors.append("title is required")
    days = concept.get("days")
    if not isinstance(days, int) or days < CONCEPT_MIN_DAYS or days > CONCEPT_MAX_DAYS:
        errors.append("days must be an int between 3 and 8")
    if not concept.get("setting"):
        errors.append("setting is required")
    if not concept.get("jedi_name"):
        errors.append("jedi_name is required")
    if not concept.get("jedi_species"):
        errors.append("jedi_species is required")
    if not concept.get("jedi_rank"):
        errors.append("jedi_rank is required")
    if not concept.get("jedi_saber"):
        errors.append("jedi_saber is required")
    if not concept.get("jedi_personality"):
        errors.append("jedi_personality is required")
    if not concept.get("jedi_target"):
        errors.append("jedi_target is required")
    tone = concept.get("tone")
    if not isinstance(tone, list) or not tone:
        errors.append("tone must be a non-empty list")

    return errors


def validate_story_prompt_inputs(
    *,
    title: str,
    num_days: int,
    setting: str,
    jedi_details: dict[str, Any],
    tone_focus: list[str],
) -> list[str]:
    errors: list[str] = []

    if not str(title or "").strip():
        errors.append("title is required")
    if not isinstance(num_days, int) or num_days < 1 or num_days > CONCEPT_MAX_DAYS:
        errors.append("num_days must be an int between 1 and 8")
    if not str(setting or "").strip():
        errors.append("setting is required")
    if not isinstance(jedi_details, dict):
        errors.append("jedi_details must be a dict")
    else:
        if not str(jedi_details.get("name", "")).strip():
            errors.append("jedi_details.name is required")
    if not isinstance(tone_focus, list) or not tone_focus:
        errors.append("tone_focus must be a non-empty list")

    return errors


def validate_outline_structure(outline: str, expected_days: int) -> list[str]:
    errors: list[str] = []
    text = str(outline or "").strip()

    if not text:
        return ["outline is empty"]

    if not re.search(r"## EPISODE ARC\s*\n", text, re.IGNORECASE):
        errors.append("missing ## EPISODE ARC section")

    day_headers = []
    for line in text.splitlines():
        if line.strip().lower().startswith("## day "):
            day_headers.append(line.strip())

    if len(day_headers) < expected_days:
        errors.append(f"expected at least {expected_days} day headers, found {len(day_headers)}")

    for day_num in range(1, expected_days + 1):
        if not re.search(rf"^## DAY {day_num}:\s*.+$", text, re.IGNORECASE | re.MULTILINE):
            errors.append(f"missing DAY {day_num} header")

    # Check that the outline contains the expected last day (truncation check)
    last_expected = f"## DAY {expected_days}:"
    if last_expected not in text:
        errors.append(f"outline appears truncated — missing {last_expected}")

    # Per-day validation using regex to extract day blocks
    day_block_pattern = r"(## DAY (\d+):.*?)(?=## DAY \d+:|$)"
    day_blocks = re.findall(day_block_pattern, text, re.DOTALL | re.IGNORECASE)
    found_days = {int(num): block for block, num in day_blocks}

    for day_num in range(1, expected_days + 1):
        block = found_days.get(day_num, "")
        if not block.strip():
            continue

        chapter_lines = re.findall(r"^\s*-\s*Chapter\s+\d+:", block, re.IGNORECASE | re.MULTILINE)
        if not MIN_CHAPTERS_PER_DAY <= len(chapter_lines) <= CHAPTERS_PER_DAY:
            errors.append(
                f"DAY {day_num}: expected {MIN_CHAPTERS_PER_DAY}-{CHAPTERS_PER_DAY} chapters, found {len(chapter_lines)}"
            )

        for chapter_block in re.finditer(
            r"^\s*-\s*Chapter\s+\d+:\s*(.*?)(?=^\s*-\s*Chapter\s+\d+:|^\s*-\s*Ending hook:|\Z)",
            block,
            re.IGNORECASE | re.MULTILINE | re.DOTALL,
        ):
            content = chapter_block.group(1).strip()
            if not content:
                errors.append(f"DAY {day_num}: Chapter has no content")
                continue
            beat_count = len(re.findall(r"\bBeat\s+\d+:", content, re.IGNORECASE))
            if not 4 <= beat_count <= 5:
                errors.append(f"DAY {day_num}: each chapter needs 4-5 beats, found {beat_count}")

        # Check ending hook
        if not re.search(r"^\s*-\s*Ending hook:\s*.+$", block, re.IGNORECASE | re.MULTILINE):
            errors.append(f"DAY {day_num}: missing Ending hook")

        # Check purpose
        if not re.search(r"^\s*-\s*Purpose:\s*.+$", block, re.IGNORECASE | re.MULTILINE):
            errors.append(f"DAY {day_num}: missing Purpose")

    return errors


def validate_outline_quality(outline: str, expected_days: int) -> list[str]:
    """Reject structurally valid outlines that would predictably produce loops."""
    errors: list[str] = []
    text = str(outline or "").strip()
    day_blocks = re.findall(
        r"(## DAY (\d+):.*?)(?=## DAY \d+:|$)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    beats: list[str] = []
    for block, _day_num in day_blocks[:expected_days]:
        for match in re.finditer(r"\bBeat\s+\d+:\s*(.+)", block, re.IGNORECASE):
            normalized = re.sub(r"[^a-z0-9]+", " ", match.group(1).lower()).strip()
            if normalized:
                beats.append(normalized)
    if not beats:
        return ["outline contains no usable beat text"]
    duplicate_count = len(beats) - len(set(beats))
    if duplicate_count > max(2, len(beats) // 10):
        errors.append(
            f"outline repeats {duplicate_count} beat(s); each chapter needs distinct actions and reversals"
        )
    chapter_blocks = re.findall(
        r"^\s*-\s*Chapter\s+\d+:\s*(.*?)(?=^\s*-\s*Chapter\s+\d+:|^\s*-\s*Ending hook:|\Z)",
        text,
        re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    signatures = []
    for chapter in chapter_blocks:
        words = re.findall(r"[a-z0-9]+", chapter.lower())
        signatures.append(" ".join(words[:18]))
    if signatures and len(set(signatures)) < max(3, len(signatures) // 2):
        errors.append("outline chapter openings are too similar to support distinct scenes")
    return errors
