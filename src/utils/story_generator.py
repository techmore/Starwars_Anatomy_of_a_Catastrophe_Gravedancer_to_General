"""Story generation logic using MLX."""

import json
import os
import re
import time
from collections.abc import Callable
from typing import Any

from src.prompts.system_prompts import STORY_GENERATION_SYSTEM_PROMPT
from src.utils.contracts import ProgressCallback, TextGenerationBackend
from src.utils.logging_utils import get_logger
from src.utils.prompt_schema import (
    DAILY_TARGET_TOKENS,
    STORY_DAY_EXPANSION_HEADER,
    STORY_DAY_HEADING,
    STORY_EPISODE_ARC_HEADER,
    STORY_EPISODE_HEADER,
    STORY_OUTLINE_HEADER,
    STORY_SECTION_EXPANSION_HEADER,
    STORY_TONE_LINE,
    TARGET_WORDS_PER_DAY,
    build_story_constraints_block,
    build_story_deepening_block,
    build_story_multi_pass_block,
    build_story_pacing_block,
    build_story_structure_block,
    build_story_word_budget,
    validate_outline_structure,
    validate_story_prompt_inputs,
)

LOGGER = get_logger(__name__)

# M1 Pro / 32 GB operational ceilings. The structured workflow generates one
# outline or chapter at a time, so these limits keep KV-cache growth and long
# runaway responses bounded while leaving enough headroom for the requested
# ~1,500-word chapter target.
# A three-day outline needs about 60 explicit beat lines; 3,000 tokens leaves
# room for the arc and headings while preventing a thinking model from
# spending many minutes on an overlong planning response.
OUTLINE_MAX_TOKENS = 5000
# Five sections/day at roughly 1,400-1,600 words/chapter is enough to meet the
# product target on memory-bound local models. Hosted runs override this via
# GRAVEDANCER_SECTION_MAX_TOKENS (the TUI sets 12000 for OpenCode) so a
# 5-chapter day can reach the ~45k-token daily target.
SECTION_MAX_TOKENS = int(os.environ.get("GRAVEDANCER_SECTION_MAX_TOKENS", "4500"))
# Prose tail handed to each section prompt ("PRIOR PROSE"). Local runs keep the
# memory-bound 1800-char ceiling; hosted runs raise it via env (the TUI sets
# 4000 for OpenCode) so chapters see more of the immediately preceding scene.
SECTION_TAIL_CHARS = int(os.environ.get("GRAVEDANCER_SECTION_TAIL_CHARS", "1800"))
# Story-together continuity: after each completed day a short recap is
# generated and injected into every later section prompt, so chapters carry
# established facts instead of relying on the prose tail alone.
RECAP_SYSTEM_PROMPT = (
    "You are a continuity clerk for serialized military science fiction. "
    "You produce terse, factual summaries a writer can rely on for consistency."
)
RECAP_MAX_TOKENS = 700
STORY_SO_FAR_MAX_CHARS = int(os.environ.get("GRAVEDANCER_STORY_SO_FAR_MAX_CHARS", "8000"))

OUTLINE_RECOVERY_ATTEMPTS = 3


def _story_so_far_enabled() -> bool:
    """Runtime toggle so long local runs can opt out of recap calls."""
    return os.environ.get("GRAVEDANCER_STORY_SO_FAR", "1").strip().lower() not in {"0", "false", "off"}


def _section_tail_chars() -> int:
    """Per-section prose tail; hosted runs raise this via GRAVEDANCER_SECTION_TAIL_CHARS."""
    raw = os.environ.get("GRAVEDANCER_SECTION_TAIL_CHARS", "").strip()
    try:
        value = int(raw) if raw else SECTION_TAIL_CHARS
    except ValueError:
        value = SECTION_TAIL_CHARS
    return max(200, value)


def _retry_outline(
    gen: Callable[[], str],
    expected_days: int,
    attempts: int,
    on_attempt: Callable[[int, int], None] | None = None,
) -> tuple[str, list[str]]:
    """Call ``gen`` until the outline validates or attempts are exhausted.

    Qwen/Gemma GGUFs served by Ollama occasionally EOS-truncate mid-structure;
    a single rebuild then killed the whole episode. Retrying the same prompt a
    few times (costing only one outline pass each) turns a hard crash into a
    transient blip. Returns ``(outline, errors)``; errors is empty on success.
    """
    outline = ""
    errors: list[str] = ["no attempt made"]
    for attempt in range(1, attempts + 1):
        if on_attempt:
            on_attempt(attempt, attempts)
        outline = gen()
        errors = validate_outline_structure(outline, expected_days=expected_days)
        if not errors:
            return outline, []
        if attempt < attempts:
            LOGGER.warning(
                "outline attempt invalid attempt=%s/%s errors=%s",
                attempt,
                attempts,
                errors[:3],
            )
    return outline, errors


class GenerationCancelled(RuntimeError):
    """Raised when a cooperative cancellation sentinel is detected."""


def _cancellation_requested() -> bool:
    """Check the optional local sentinel between model requests."""
    sentinel = os.environ.get("GRAVEDANCER_CANCEL_FILE", "").strip()
    return bool(sentinel) and os.path.isfile(os.path.expanduser(sentinel))


def outline_token_budget(num_days: int, requested: int | None = None) -> int:
    """Choose enough outline budget for all requested days without runaway output."""
    if requested:
        return requested
    # Five chapters × four beats per day plus headings, purposes, and hooks.
    # Keep the cap below the LM Studio ceiling used by the local workflow.
    return min(8000, max(OUTLINE_MAX_TOKENS, int(num_days) * 1400))


class StoryGenerator:
    def __init__(self, mlx_client: TextGenerationBackend):
        self.mlx = mlx_client
    
    def build_prompt(
        self,
        title: str,
        num_days: int,
        jedi_details: dict[str, str],
        setting: str,
        tone_focus: list[str],
        additional_instructions: str
    ) -> str:
        """Build the user prompt for story generation."""
        errors = validate_story_prompt_inputs(
            title=title,
            num_days=num_days,
            setting=setting,
            jedi_details=jedi_details,
            tone_focus=tone_focus,
        )
        if errors:
            raise ValueError(f"Invalid story prompt inputs: {', '.join(errors)}")
        
        jedi_section = ""
        if jedi_details.get("name"):
            jedi_section = (
                f"\n**JEDI TARGET:**\n"
                f"- Name: {jedi_details.get('name', 'Unknown')}\n"
                f"- Species: {jedi_details.get('species', 'Unknown')}\n"
                f"- Rank: {jedi_details.get('rank', 'Unknown')}\n"
                f"- Lightsaber Color: {jedi_details.get('lightsaber_color', 'Unknown')}\n"
                f"- Personality/Ability: {jedi_details.get('personality', 'Unknown')}\n"
                f"- Why Targeted: {jedi_details.get('why_targeted', 'Unknown')}"
            )
        tone_section = f"\n{STORY_TONE_LINE.format(tone=', '.join(tone_focus))}" if tone_focus else ""
        additional_section = f"\n**ADDITIONAL INSTRUCTIONS:**\n{additional_instructions}" if additional_instructions.strip() else ""
        prompt = f"""{STORY_EPISODE_HEADER}

**EPISODE TITLE:** {title}
**NUMBER OF DAYS:** {num_days}
**SETTING / PLANET:** {setting}{jedi_section}{tone_section}{additional_section}

{build_story_constraints_block(num_days)}

{build_story_multi_pass_block()}

**NOVELLA STRUCTURE REQUIRED:**
{build_story_structure_block()}

{build_story_deepening_block()}

{build_story_pacing_block()}

If the model starts to ramble, compress, repeat, or drift, restart the scene around the next concrete micro-beat instead of adding filler.

Use the writing style described in your system prompt: cinematic, visceral, atmospheric, with internal monologue, sparse dialogue, the hiss of servos, weight of durasteel, hum of lightsabers in rain.

Begin with "{STORY_DAY_HEADING.format(day_number=1)}" and continue through "{STORY_DAY_HEADING.format(day_number=num_days)}"."""
        return prompt

    def build_outline_prompt(
        self,
        title: str,
        num_days: int,
        jedi_details: dict[str, str],
        setting: str,
        tone_focus: list[str],
        additional_instructions: str,
    ) -> str:
        """Build a structured planning prompt for the full episode."""
        errors = validate_story_prompt_inputs(
            title=title,
            num_days=num_days,
            setting=setting,
            jedi_details=jedi_details,
            tone_focus=tone_focus,
        )
        if errors:
            raise ValueError(f"Invalid outline prompt inputs: {', '.join(errors)}")
        tone_section = f"\n{STORY_TONE_LINE.format(tone=', '.join(tone_focus))}" if tone_focus else ""
        additional_section = f"\n**ADDITIONAL INSTRUCTIONS:**\n{additional_instructions}" if additional_instructions.strip() else ""
        jedi_section = f"\n**JEDI TARGET:** {json.dumps(jedi_details, ensure_ascii=False, indent=2)}" if jedi_details else ""
        return f"""{STORY_OUTLINE_HEADER.format(num_days=num_days)}

**EPISODE TITLE:** {title}
**SETTING / PLANET:** {setting}{jedi_section}{tone_section}{additional_section}

Return a structured outline with TWO sections:

### 1. Episode Arc (first)
{STORY_EPISODE_ARC_HEADER}
[Write 3-5 sentences describing the episode's overall shape: the thematic spine, the Jedi's philosophy, the arc Qymaen will travel, and how it ends. This sets context for every day below.]

### 2. Day Outlines (after the arc)
Each day must have this format:
## DAY 1: [Short Title]
- Purpose: [why this day matters in the episode arc]
- Chapter 1:
  - Beat 1: [one concise sentence]
  - Beat 2: [one concise sentence]
  - Beat 3: [one concise sentence]
  - Beat 4: [one concise sentence]
- Chapter 2:
  - Beat 1: [one concise sentence]
  - Beat 2: [one concise sentence]
  - Beat 3: [one concise sentence]
  - Beat 4: [one concise sentence]
- Chapter 3:
  - Beat 1: [one concise sentence]
  - Beat 2: [one concise sentence]
  - Beat 3: [one concise sentence]
  - Beat 4: [one concise sentence]
- Chapter 4: [same four-beat format]
- Chapter 5: [same four-beat format]
- Ending hook: [1-2 sentences — what pulls the reader into the next day]

Rules:
- The outline must include ALL requested days, in order, with no omissions.
- Do not stop after Day 1 or Day 2. Continue until every day is present.
- Each day must have exactly 5 chapters. Each chapter must have exactly 4 concise beats. Each beat should be specific enough that a later expansion pass can write prose from it without inventing new plot turns.
- Make the beats explicit with "Beat 1", "Beat 2", etc. under every chapter.
- Every day must include an ending hook, even if it is only one sentence.
- Treat each day as a self-contained thriller chapter with its own escalation arc.
- The final day must resolve the episode arc decisively.
- Keep the overall episode arc coherent across all days.
- Preserve continuity of locations, injuries, emotional state, and Jedi capabilities.
- Use the beats to stage the day's internal rhythm: setup, pressure, escalation, reversal, hook.
- Keep Day 1 setup strong and the final day decisive.
- The final outcome is determined by the approved concept. A kill is optional;
  allowed outcomes include death, escape, partial victory, continuing pursuit,
  the Jedi turning the tables, or a transformation choice.
- Do NOT include meta-commentary, notes, or thinking before the episode arc. Start directly with "{STORY_EPISODE_ARC_HEADER}".
{additional_section}
"""

    def build_day_expansion_prompt(
        self,
        title: str,
        num_days: int,
        outline: str,
        day_number: int,
        day_outline: str,
        day_draft: str,
        previous_day: str,
        jedi_details: dict[str, str],
        setting: str,
        tone_focus: list[str],
        additional_instructions: str,
    ) -> str:
        """Build a focused prompt to expand one outlined day into prose."""
        errors = validate_story_prompt_inputs(
            title=title,
            num_days=num_days,
            setting=setting,
            jedi_details=jedi_details,
            tone_focus=tone_focus,
        )
        if errors:
            raise ValueError(f"Invalid day expansion inputs: {', '.join(errors)}")
        tone_section = f"\n{STORY_TONE_LINE.format(tone=', '.join(tone_focus))}" if tone_focus else ""
        additional_section = f"\n**ADDITIONAL INSTRUCTIONS:**\n{additional_instructions}" if additional_instructions.strip() else ""
        prev_section = f"\n**PREVIOUS DAY CONTEXT (immediately before Day {day_number}):**\n{previous_day}" if previous_day.strip() else ""
        draft_section = f"\n**DAY {day_number} DRAFT:**\n{day_draft}" if day_draft.strip() else ""
        episode_arc = self.parse_episode_arc(outline)
        arc_section = f"\n**EPISODE ARC:**\n{episode_arc}" if episode_arc else ""
        return f"""{STORY_DAY_EXPANSION_HEADER.format(day_number=day_number)}

**EPISODE TITLE:** {title}
**TOTAL DAYS:** {num_days}
**SETTING / PLANET:** {setting}
**JEDI TARGET:** {json.dumps(jedi_details, ensure_ascii=False, indent=2)}
{tone_section}{additional_section}
{arc_section}

**DAY {day_number} OUTLINE:**
{day_outline}
{draft_section}
{prev_section}

Write only the prose for Day {day_number}, with the heading:
## DAY {day_number}: [Descriptive Title]

Requirements:
- Write approximately {DAILY_TARGET_TOKENS:,} output tokens for this day (roughly {TARGET_WORDS_PER_DAY:,} words).
- Expand each chapter into a distinct scene sequence.
- Keep the chapters from the outline in order.
- Turn each chapter into a small cause-and-effect micro-sequence instead of a vague mood paragraph.
- Do not invent new major plot turns.
- Maintain continuity with prior days and the episode arc.
- Use thriller pacing, tactical detail, sensory immersion, and cinematic dialogue.
- End on the specified hook or a stronger equivalent that stays faithful to the outline.
"""

    def build_section_expansion_prompt(
        self,
        title: str,
        num_days: int,
        outline: str,
        day_number: int,
        section_index: int,
        section_count: int,
        section_outline: str,
        prior_text: str,
        day_outline: str,
        jedi_details: dict[str, str],
        setting: str,
        tone_focus: list[str],
        additional_instructions: str,
        story_so_far: str = "",
    ) -> str:
        """Build a focused prompt to expand one chapter outline into prose."""
        errors = validate_story_prompt_inputs(
            title=title,
            num_days=num_days,
            setting=setting,
            jedi_details=jedi_details,
            tone_focus=tone_focus,
        )
        if errors:
            raise ValueError(f"Invalid section expansion inputs: {', '.join(errors)}")
        tone_section = f"\n{STORY_TONE_LINE.format(tone=', '.join(tone_focus))}" if tone_focus else ""
        additional_section = f"\n**ADDITIONAL INSTRUCTIONS:**\n{additional_instructions}" if additional_instructions.strip() else ""
        prior_section = f"\n**PRIOR PROSE:**\n{prior_text}" if prior_text.strip() else ""
        summary_section = f"\n**STORY SO FAR (completed earlier days):**\n{story_so_far.strip()}" if story_so_far.strip() else ""
        episode_arc = self.parse_episode_arc(outline)
        arc_section = f"\n**EPISODE ARC:**\n{episode_arc}" if episode_arc else ""
        section_word_target = TARGET_WORDS_PER_DAY // max(section_count, 1)
        return f"""{STORY_SECTION_EXPANSION_HEADER.format(section_index=section_index, day_number=day_number)}

**EPISODE TITLE:** {title}
**TOTAL DAYS:** {num_days}
**SETTING / PLANET:** {setting}
**JEDI TARGET:** {json.dumps(jedi_details, ensure_ascii=False, indent=2)}
{tone_section}{additional_section}
{arc_section}{summary_section}

**SECTION {section_index} OUTLINE:**
{section_outline}
{prior_section}

Write only the prose for this section. Begin with a Markdown chapter heading in
this form, using a short descriptive title based on the approved outline:
### Chapter {section_index}: [Descriptive Title]
Then write the prose. Requirements:
- Continue the story seamlessly from the prior prose.
- Honor every fact in STORY SO FAR (names, injuries, objects, promises, unresolved threads); never contradict earlier days.
- Keep this section focused on the provided outline.
- Do not invent a new major beat.
- Do not repeat sentences, beats, or phrasing from the prior prose unless the repetition is intentionally dramatic and introduces new information.
- Never repeat an entire paragraph, sentence, dialogue exchange, or action sequence within this section. If a beat is complete, advance to the next beat or stop; do not fill the token budget.
- Every paragraph must introduce a new physical action, sensory change, decision, revelation, or consequence. Do not use stock loops such as "He paused", "The Jedi's shield held", or repeated statements of the same intention.
- Treat the four beats as a one-way cause-and-effect sequence. The section must not return to an earlier beat or reset the same confrontation.
- Write vivid, cinematic prose with thriller pacing.
- Preserve names, injuries, object locations, and emotional state.
- Write approximately {section_word_target:,} words for this section.
- Structure the section as a compact chapter with 2-4 micro-beat-sized movements.
- Do not add a new chapter heading or a Day heading inside the section.
"""

    def build_day_recap_prompt(self, title: str, day_number: int, day_text: str) -> str:
        """Build the continuity-digest prompt for a completed day."""
        return f"""Summarize Day {day_number} of "{title}" as a continuity digest for future writing passes.

**DAY {day_number} TEXT:**
{day_text}

Return 4-6 sentences of plain prose — no headings, no bullet points — covering only:
- Where the story now stands (location, time of day).
- Qymaen's physical and emotional state, including any new injuries or equipment.
- The Jedi's status, tactics observed, and current position.
- New objects, promises, threats, or unresolved threads left open.
- The exact situation at the day's final moment.

Do not retell the plot beat-by-beat. Do not comment on style or quality. Facts only."""

    def generate_day_recap(
        self,
        model: str,
        title: str,
        day_number: int,
        day_text: str,
        system_prompt: str | None = None,
    ) -> str:
        """Summarize a completed day into a compact continuity digest."""
        prompt = self.build_day_recap_prompt(title=title, day_number=day_number, day_text=day_text)
        system = system_prompt or RECAP_SYSTEM_PROMPT
        LOGGER.info(
            "day recap start title=%s day=%s model=%s prompt_chars=%s",
            title,
            day_number,
            model,
            len(prompt),
        )
        result = self.mlx.generate(
            model=model,
            prompt=prompt,
            system=system,
            temperature=0.2,
            max_tokens=RECAP_MAX_TOKENS,
        )
        return (result or "").strip()

    def generate_story(
        self,
        model: str,
        title: str,
        num_days: int,
        jedi_details: dict[str, str],
        setting: str,
        tone_focus: list[str],
        additional_instructions: str,
        temperature: float = 0.8,
        system_prompt: str | None = None
    ) -> str:
        """Generate a complete story.

        Compatibility shim for older callers. The main app path uses
        generate_episode_story_multi_pass() so the outline/day/section
        structure stays explicit during generation.
        """
        prompt = self.build_prompt(
            title, num_days, jedi_details, setting, tone_focus, additional_instructions
        )
        system = system_prompt or STORY_GENERATION_SYSTEM_PROMPT

        # Legacy single-pass budget: one request for the whole episode.
        # Behavior preserved from prior releases; HTTP backends clamp this to
        # their own output ceiling (e.g. LM Studio's 8192).
        max_tokens = max(12000, num_days * 11000)
        
        LOGGER.warning(
            "story generate legacy single-pass path title=%s days=%s model=%s max_tokens=%s",
            title,
            num_days,
            model,
            max_tokens,
        )
        return self.mlx.generate(
            model=model,
            prompt=prompt,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens
        )

    def generate_episode_outline(
        self,
        model: str,
        title: str,
        num_days: int,
        jedi_details: dict[str, str],
        setting: str,
        tone_focus: list[str],
        additional_instructions: str,
        temperature: float = 0.5,
        system_prompt: str | None = None,
        progress_callback: ProgressCallback | None = None,
        max_tokens: int | None = None,
    ) -> str:
        prompt = self.build_outline_prompt(title, num_days, jedi_details, setting, tone_focus, additional_instructions)
        system = system_prompt or STORY_GENERATION_SYSTEM_PROMPT
        max_tokens = outline_token_budget(num_days, max_tokens)
        LOGGER.info(
            "story outline start title=%s days=%s model=%s prompt_chars=%s system_chars=%s max_tokens=%s temperature=%.2f",
            title,
            num_days,
            model,
            len(prompt),
            len(system or ""),
            max_tokens,
            temperature,
        )
        start = time.perf_counter()
        if progress_callback:
            chunks: list[str] = []
            # Throttled snapshot join — see _stream_generate for rationale.
            last_snapshot = 0.0
            for chunk in self.mlx.generate_stream(
                model=model, prompt=prompt, system=system,
                temperature=temperature, max_tokens=max_tokens,
            ):
                chunks.append(chunk)
                now = time.perf_counter()
                if now - last_snapshot >= 0.5:
                    last_snapshot = now
                    progress_callback(stage="outline", message="Building episode outline...", text="".join(chunks))
                else:
                    progress_callback(stage="outline", message="Building episode outline...")
            outline = "".join(chunks)
        else:
            outline = self.mlx.generate(model=model, prompt=prompt, system=system, temperature=temperature, max_tokens=max_tokens)
        LOGGER.info("story outline end title=%s days=%s model=%s elapsed=%.3fs output_chars=%s", title, num_days, model, time.perf_counter() - start, len(outline))
        return outline

    def generate_episode_story_multi_pass(
        self,
        model: str,
        title: str,
        num_days: int,
        jedi_details: dict[str, str],
        setting: str,
        tone_focus: list[str],
        additional_instructions: str,
        temperature: float = 0.8,
        system_prompt: str | None = None,
        outline: str | None = None,
        day_drafts: dict[int, str] | None = None,
        day_recaps: dict[int, str] | None = None,
        recap_model: str | None = None,
        draft_only: bool = False,
        progress_callback: ProgressCallback | None = None,
        outline_max_tokens: int | None = None,
        section_max_tokens: int | None = None,
        checkpoint_callback: Callable[[int, str, str], None] | None = None,
    ) -> str:
        """Generate outline first, then expand each day.

        Continuity: a short recap is generated at each day boundary and every
        later section prompt receives the running "story so far" digest in
        addition to the prose tail. ``day_recaps`` seeds previously stored
        recaps (checkpoint resume) so resumed runs keep the same context.
        """
        LOGGER.info(
            "multi-pass start title=%s days=%s model=%s outline_present=%s draft_only=%s temperature=%.2f",
            title,
            num_days,
            model,
            bool(outline),
            draft_only,
            temperature,
        )
        start_all = time.perf_counter()
        def _emit(stage: str, message: str, text: str = "") -> None:
            if progress_callback:
                progress_callback(stage=stage, message=message, text=text)

        def _stream_generate(
            *,
            stage: str,
            message: str,
            model: str,
            prompt: str,
            system_prompt: str | None,
            temperature: float,
            max_tokens: int,
        ) -> str:
            _emit(stage, message)
            chunks: list[str] = []
            # Joining every chunk is O(n^2) across a long stream; consumers
            # only sample the text on a timer, so refresh the snapshot at
            # most twice per second and emit without text in between.
            last_snapshot = 0.0
            text_snapshot = ""
            for chunk in self.mlx.generate_stream(
                model=model,
                prompt=prompt,
                system=system_prompt or STORY_GENERATION_SYSTEM_PROMPT,
                temperature=temperature,
                max_tokens=max_tokens,
            ):
                chunks.append(chunk)
                now = time.perf_counter()
                if now - last_snapshot >= 0.5:
                    text_snapshot = "".join(chunks)
                    last_snapshot = now
                    _emit(stage, message, text_snapshot)
                else:
                    _emit(stage, message)
            return "".join(chunks)

        if not outline:
            outline_start = time.perf_counter()
            LOGGER.info(
                "outline pass begin title=%s days=%s model=%s temperature=%.2f max_tokens=%s",
                title,
                num_days,
                model,
                max(0.2, temperature - 0.2),
                OUTLINE_MAX_TOKENS,
            )
            def _gen_outline() -> str:
                return _stream_generate(
                    stage="outline",
                    message="Building episode outline...",
                    model=model,
                    prompt=self.build_outline_prompt(
                        title=title,
                        num_days=num_days,
                        jedi_details=jedi_details,
                        setting=setting,
                        tone_focus=tone_focus,
                        additional_instructions=additional_instructions,
                    ),
                    system_prompt=system_prompt,
                    temperature=max(0.2, temperature - 0.2),
                    max_tokens=outline_token_budget(num_days, outline_max_tokens),
                )

            def _on_outline_attempt(attempt: int, total: int) -> None:
                if attempt > 1:
                    _emit("outline", f"Outline incomplete — retrying ({attempt}/{total})...")

            outline, outline_errors = _retry_outline(
                _gen_outline, num_days, OUTLINE_RECOVERY_ATTEMPTS, _on_outline_attempt
            )
            if outline_errors:
                raise ValueError(
                    f"Invalid outline structure after {OUTLINE_RECOVERY_ATTEMPTS} attempts: {', '.join(outline_errors)}"
                )
            LOGGER.info(
                "outline pass end title=%s days=%s chars=%s elapsed=%.3fs",
                title,
                num_days,
                len(outline),
                time.perf_counter() - outline_start,
            )
            _emit("outline", f"Outline ready ({len(outline):,} chars).")
        else:
            outline_errors = validate_outline_structure(outline, expected_days=num_days)
            if outline_errors:
                LOGGER.warning(
                    "Discarding invalid cached outline title=%s days=%s errors=%s",
                    title,
                    num_days,
                    outline_errors,
                )
                _emit("outline", "Cached outline was incomplete; rebuilding the outline.")
                outline_start = time.perf_counter()
                LOGGER.info(
                    "outline recovery pass begin title=%s days=%s model=%s max_tokens=%s",
                    title,
                    num_days,
                    model,
                    outline_token_budget(num_days, outline_max_tokens),
                )

                def _gen_recovered() -> str:
                    return _stream_generate(
                        stage="outline",
                        message="Rebuilding incomplete outline...",
                        model=model,
                        prompt=self.build_outline_prompt(
                            title=title,
                            num_days=num_days,
                            jedi_details=jedi_details,
                            setting=setting,
                            tone_focus=tone_focus,
                            additional_instructions=additional_instructions,
                        ),
                        system_prompt=system_prompt,
                        temperature=max(0.2, temperature - 0.2),
                        max_tokens=outline_token_budget(num_days, outline_max_tokens),
                    )

                def _on_recover_attempt(attempt: int, total: int) -> None:
                    if attempt > 1:
                        _emit("outline", f"Rebuild incomplete — retrying ({attempt}/{total})...")

                outline, outline_errors = _retry_outline(
                    _gen_recovered, num_days, OUTLINE_RECOVERY_ATTEMPTS, _on_recover_attempt
                )
                if outline_errors:
                    raise ValueError(
                        f"Invalid rebuilt outline structure after {OUTLINE_RECOVERY_ATTEMPTS} attempts: {', '.join(outline_errors)}"
                    )
                LOGGER.info(
                    "outline recovery pass end title=%s days=%s chars=%s elapsed=%.3fs",
                    title,
                    num_days,
                    len(outline),
                    time.perf_counter() - outline_start,
                )
        day_blocks = self._split_outline_days(outline)
        day_stories: list[str] = []
        previous_day = ""
        recaps_enabled = _story_so_far_enabled()
        recap_entries: list[str] = []
        seen_recap_days: set = set()

        def _append_recap(day_number: int, recap_text: str) -> None:
            clean = (recap_text or "").strip()
            if not clean or day_number in seen_recap_days:
                return
            seen_recap_days.add(day_number)
            recap_entries.append(f"**Day {day_number}:** {clean}")

        def _story_so_far_text() -> str:
            if not recap_entries:
                return ""
            joined = "\n\n".join(recap_entries)
            if len(joined) <= STORY_SO_FAR_MAX_CHARS:
                return joined
            trimmed: list[str] = []
            budget = STORY_SO_FAR_MAX_CHARS
            for entry in reversed(recap_entries):
                if budget <= 0:
                    break
                trimmed.append(entry)
                budget -= len(entry) + 2
            return "\n\n".join(reversed(trimmed))

        for day_number in range(1, num_days + 1):
            if _cancellation_requested():
                raise GenerationCancelled("Generation cancelled before the next day; checkpoint preserved.")
            day_outline = day_blocks.get(day_number, "").strip()
            day_draft = (day_drafts or {}).get(day_number, "")
            this_day_recap = ""
            _emit("day", f"Expanding Day {day_number}/{num_days}...")
            day_start = time.perf_counter()
            LOGGER.info(
                "day pass begin title=%s day=%s/%s outline_chars=%s draft_chars=%s previous_day_chars=%s",
                title,
                day_number,
                num_days,
                len(day_outline),
                len(day_draft),
                len(previous_day),
            )
            if draft_only and day_draft.strip():
                _emit("checkpoint", f"Reusing checkpoint for Day {day_number}.")
                LOGGER.info("day checkpoint reused title=%s day=%s draft_chars=%s", title, day_number, len(day_draft))
                day_text = day_draft.strip()
                reused_draft = True
                if recaps_enabled:
                    stored = (day_recaps or {}).get(day_number, "").strip()
                    _append_recap(day_number, stored)
                    this_day_recap = stored
            else:
                reused_draft = False
                section_blocks = self._split_day_sections(day_outline)
                section_texts: list[str] = []
                # Keep only a short continuity tail so the model does not start echoing prior sections.
                prior_text = self._tail_for_context(previous_day, max_chars=max(2500, _section_tail_chars()))
                LOGGER.info("day section loop begin title=%s day=%s section_count=%s", title, day_number, len(section_blocks))
                for section_index, section_outline in enumerate(section_blocks, start=1):
                    if _cancellation_requested():
                        raise GenerationCancelled("Generation cancelled before the next section; checkpoint preserved.")
                    _emit("section", f"Day {day_number}: expanding section {section_index}/{len(section_blocks)}")
                    section_start = time.perf_counter()
                    context_tail = self._tail_for_context(prior_text, max_chars=_section_tail_chars())
                    LOGGER.info(
                        "section pass begin title=%s day=%s section=%s/%s section_chars=%s prior_chars=%s",
                        title,
                        day_number,
                        section_index,
                        len(section_blocks),
                        len(section_outline),
                        len(context_tail),
                    )
                    section_prompt = self.build_section_expansion_prompt(
                        title=title,
                        num_days=num_days,
                        outline=outline,
                        day_number=day_number,
                        section_index=section_index,
                        section_count=len(section_blocks),
                        section_outline=section_outline,
                        prior_text=context_tail,
                        story_so_far=_story_so_far_text(),
                        day_outline=day_outline,
                        jedi_details=jedi_details,
                        setting=setting,
                        tone_focus=tone_focus,
                        additional_instructions=additional_instructions,
                    )
                    section_text = _stream_generate(
                        stage=f"day-{day_number}-section-{section_index}",
                        message=f"Streaming Day {day_number} section {section_index}...",
                        model=model,
                        prompt=section_prompt,
                        system_prompt=system_prompt,
                        temperature=temperature,
                        max_tokens=section_max_tokens or SECTION_MAX_TOKENS,
                    )
                    section_text = self._strip_embedded_day_headings(section_text)
                    section_texts.append(section_text.strip())
                    prior_text = self._tail_for_context(section_text, max_chars=max(2500, _section_tail_chars()))
                    section_word_count = len(section_text.split())
                    section_word_target = TARGET_WORDS_PER_DAY // max(len(section_blocks), 1)
                    LOGGER.info(
                        "section pass end title=%s day=%s section=%s elapsed=%.3fs output_words=%s word_ratio=%.2f",
                        title,
                        day_number,
                        section_index,
                        time.perf_counter() - section_start,
                        section_word_count,
                        section_word_count / max(section_word_target, 1),
                    )
                day_text = "\n\n".join(section_texts)
                LOGGER.info(
                    "continuity pass skipped title=%s day=%s section_output_chars=%s",
                    title,
                    day_number,
                    len(day_text),
                )
            if not day_text.lstrip().startswith(f"## DAY {day_number}:"):
                day_title = self._extract_day_title(day_outline, day_number)
                day_text = f"## DAY {day_number}: {day_title}\n\n{day_text.strip()}"
            day_stories.append(day_text.strip())
            previous_day = day_text.strip()
            if recaps_enabled and not reused_draft:
                _emit("recap", f"Summarizing Day {day_number} for continuity...")
                recap_start = time.perf_counter()
                try:
                    this_day_recap = self.generate_day_recap(
                        model=recap_model or model,
                        title=title,
                        day_number=day_number,
                        day_text=day_text,
                    )
                    _append_recap(day_number, this_day_recap)
                    LOGGER.info(
                        "day recap end title=%s day=%s chars=%s elapsed=%.3fs",
                        title,
                        day_number,
                        len(this_day_recap),
                        time.perf_counter() - recap_start,
                    )
                except Exception as exc:
                    LOGGER.warning(
                        "day recap failed title=%s day=%s error=%s",
                        title,
                        day_number,
                        exc,
                    )
            if checkpoint_callback:
                checkpoint_callback(day_number, day_text.strip(), this_day_recap)
            day_word_count = len(day_text.split())
            day_word_ratio = day_word_count / TARGET_WORDS_PER_DAY
            LOGGER.info(
                "day pass end title=%s day=%s elapsed=%.3fs output_words=%s word_ratio=%.2f target=%s cumulative_words=%s",
                title,
                day_number,
                time.perf_counter() - day_start,
                day_word_count,
                day_word_ratio,
                TARGET_WORDS_PER_DAY,
                sum(len(part.split()) for part in day_stories),
            )
            _emit("day", f"Day {day_number} complete ({len(day_text):,} chars).")
        total_words = sum(len(part.split()) for part in day_stories)
        total_target = TARGET_WORDS_PER_DAY * num_days
        LOGGER.info(
            "multi-pass end title=%s days=%s elapsed=%.3fs output_words=%s target_words=%s word_ratio=%.2f",
            title,
            num_days,
            time.perf_counter() - start_all,
            total_words,
            total_target,
            total_words / max(total_target, 1),
        )
        return "\n\n".join(day_stories)

    def _split_outline_days(self, outline: str) -> dict[int, str]:
        blocks: dict[int, str] = {}
        pattern = r"(## DAY (\d+):.*?)(?=## DAY \d+:|$)"
        for block, day_num in re.findall(pattern, outline, re.DOTALL | re.IGNORECASE):
            blocks[int(day_num)] = block.strip()
        return blocks

    def _split_day_sections(self, day_outline: str) -> list[str]:
        """Extract chapter outline blocks from a day outline block."""
        text = day_outline.strip()
        if not text:
            return []
        chapter_pattern = r"(?:^- Chapter\s+\d+:\s*.*?)(?=^- Chapter\s+\d+:|^- Ending hook:|\Z)"
        chapter_blocks = [
            block.strip()
            for block in re.findall(chapter_pattern, text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
            if block.strip()
        ]
        if chapter_blocks:
            return [self._normalize_chapter_outline(block) for block in chapter_blocks]
        return [text]

    def _normalize_chapter_outline(self, chapter_outline: str) -> str:
        """Ensure a chapter outline has explicit beat markers when possible.

        If the model wrote prose-like chapter guidance without beat labels,
        this heuristically splits it into labeled beats without inventing
        repeated filler text.
        """
        text = chapter_outline.strip()
        if not text:
            return text
        if re.search(r"\bBeat\s+\d+:", text, re.IGNORECASE):
            return text

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return text

        header = lines[0]
        body = " ".join(lines[1:]).strip()
        if not body:
            return text

        sentences = re.split(r"(?<=[.!?])\s+", body)
        sentences = [s.strip() for s in sentences if s.strip()]
        if not sentences:
            sentences = [body]

        beat_count = min(max(len(sentences), 4), 8)
        chunks: list[str] = []
        for idx in range(beat_count):
            if idx >= len(sentences):
                break
            sentence = sentences[idx]
            chunks.append(f"- Beat {idx + 1}: {sentence}")
        return "\n".join([header, *chunks])

    def _tail_for_context(self, text: str, max_chars: int = 2500) -> str:
        """Keep only the most recent prose for continuity without echoing the whole section."""
        clean = text.strip()
        if len(clean) <= max_chars:
            return clean
        tail = clean[-max_chars:]
        cut = tail.find("\n\n")
        return tail[cut + 2 :] if cut != -1 and cut + 2 < len(tail) else tail

    def _strip_embedded_day_headings(self, text: str) -> str:
        """Remove model-added day headings from chapter-only generation.

        The caller owns the single ``## DAY n`` heading.  Leaving headings
        emitted by individual chapter calls in place makes viewers interpret
        one day as several separate days.
        """
        return re.sub(r"(?im)^\s*##\s*DAY\s+\d+\s*:[^\n]*\n?", "", text).strip()

    def _extract_day_title(self, day_outline: str, day_number: int) -> str:
        first_line = next((line.strip() for line in day_outline.splitlines() if line.strip()), "")
        match = re.match(rf"## DAY {day_number}:\s*(.*)", first_line, re.IGNORECASE)
        if match and match.group(1).strip():
            return match.group(1).strip()
        return f"Day {day_number}"

    def parse_episode_arc(self, outline: str) -> str:
        """Extract the episode arc summary from the outline."""
        match = re.search(
            r"## EPISODE ARC\s*\n(.*?)(?=\n## DAY \d+:|\Z)",
            outline, re.DOTALL | re.IGNORECASE,
        )
        if match:
            return match.group(1).strip()
        return ""

    def parse_outline_days(self, outline: str) -> list[dict[str, Any]]:
        """Parse an outline into day blocks and section outlines."""
        days: list[dict[str, Any]] = []
        day_pattern = r"## DAY (\d+):\s*(.*?)(?=## DAY \d+:|$)"
        for day_num, block in re.findall(day_pattern, outline, re.DOTALL | re.IGNORECASE):
            lines = [line.strip() for line in block.splitlines() if line.strip()]
            title = self._extract_day_title(f"## DAY {day_num}:\n{block}", day_num)
            sections = self._parse_day_sections(lines)
            purpose = ""
            for line in lines:
                lower_stripped = line.lstrip("- \t").lower()
                if lower_stripped.startswith("purpose"):
                    purpose = line.lstrip("- \t").split(":", 1)[1].strip() if ":" in line else ""
                    break
            hook = ""
            for line in lines:
                lower_stripped = line.lstrip("- \t").lower()
                if lower_stripped.startswith("ending hook"):
                    hook = line.lstrip("- \t").split(":", 1)[1].strip() if ":" in line else ""
                    break
            days.append(
                {
                    "number": int(day_num),
                    "title": title,
                    "purpose": purpose,
                    "sections": sections,
                    "ending_hook": hook,
                    "raw": f"## DAY {day_num}:\n{block.strip()}",
                }
            )
        return days

    def _parse_day_sections(self, lines: list[str]) -> list[dict[str, str]]:
        """Parse chapter lines into editable outline blocks."""
        sections: list[dict[str, str]] = []
        current: dict[str, str] | None = None
        for line in lines:
            lower = line.lower()
            if lower.startswith("- chapter"):
                if current:
                    sections.append(current)
                current = {"label": line.lstrip("- ").strip(), "text": line.lstrip("- ").strip()}
            elif current and not lower.startswith("- ending hook") and not lower.startswith("- purpose"):
                current["text"] = f"{current['text']} {line}".strip()
            elif lower.startswith("- ending hook") and current:
                sections.append(current)
                current = None
        if current:
            sections.append(current)
        return sections

    def regenerate_day(
        self,
        model: str,
        day_number: int,
        full_story: str,
        title: str,
        num_days: int,
        jedi_details: dict[str, str],
        setting: str,
        tone_focus: list[str],
        additional_instructions: str,
        temperature: float = 0.8,
        system_prompt: str | None = None
    ) -> str:
        """Regenerate a specific day."""
        # Extract context from other days
        day_pattern = rf"## DAY {day_number}:.*?(?=## DAY \d+:|$)"
        match = re.search(day_pattern, full_story, re.DOTALL)
        old_day = match.group(0).strip() if match else ""
        
        # Build context from other days
        other_days = re.sub(day_pattern, "", full_story, flags=re.DOTALL)
        
        regen_prompt = f"""Regenerate ONLY Day {day_number} of this episode. Keep all other days exactly as written.

**EPISODE TITLE:** {title}
**TOTAL DAYS:** {num_days}
**SETTING:** {setting}
**JEDI TARGET:** {jedi_details.get('name', 'Unknown')} ({jedi_details.get('species', 'Unknown')})

**OTHER DAYS (CONTEXT - DO NOT CHANGE):**
{other_days}

**OLD DAY {day_number} (REPLACE THIS):**
{old_day}

        Write a NEW Day {day_number} with a descriptive title. **Target: ~{build_story_word_budget(num_days):,} words for this day** (3-5 scenes per day). Maintain continuity with previous/next days. Same quality, sensory depth, character interiority, tactical detail, and thematic resonance. The day should advance the novella's transformation arc and thematic spine. Focus on: {', '.join(tone_focus) if tone_focus else 'action and dread'}."""
        
        system = system_prompt or STORY_GENERATION_SYSTEM_PROMPT
        
        # Allow comfortable headroom for a single long day.
        day_target_tokens = 14000
        LOGGER.info("regenerate day=%s title=%s model=%s", day_number, title, model)
        new_day = self.mlx.generate(
            model=model,
            prompt=regen_prompt,
            system=system,
            temperature=temperature,
            max_tokens=day_target_tokens
        )
        
        # Replace the day in the full story
        if match:
            new_story = full_story[:match.start()] + new_day + full_story[match.end():]
        else:
            new_story = full_story + f"\n\n## DAY {day_number}: Regenerated\n\n" + new_day
        
        return new_story
    
    def parse_days(self, story: str) -> list[dict[str, str]]:
        """Parse story into day sections. Each day includes `word_count`."""
        days = []
        pattern = r"^## DAY (\d+):\s*(.*?)(?=^## DAY \d+:|\Z)"
        matches = re.findall(pattern, story, re.DOTALL | re.IGNORECASE | re.MULTILINE)
        
        for day_num, content in matches:
            text = content.strip()
            lines = text.split("\n")
            title = lines[0].strip() if lines else f"Day {day_num}"
            days.append({
                "number": int(day_num),
                "title": title,
                "content": text,
                "word_count": len(text.split()),
            })
        
        return days
    
    def get_stats(self, story: str) -> dict[str, Any]:
        """Get story statistics."""
        words = len(story.split())
        reading_time = max(1, round(words / 200))  # 200 wpm

        days = self.parse_days(story)

        return {
            "word_count": words,
            "reading_time_minutes": reading_time,
            "num_days": len(days),
            "days": days
        }

    def build_critique_prompt(
        self,
        full_story: str,
        outline: str,
        title: str,
        num_days: int,
        jedi_details: dict[str, str],
        setting: str,
        tone_focus: list[str],
    ) -> str:
        """Build a prompt that asks the model to rate and critique the episode."""
        tone_section = f"\n**TONE / FOCUS:** {', '.join(tone_focus)}" if tone_focus else ""
        episode_arc = self.parse_episode_arc(outline)
        arc_section = f"\n**EPISODE ARC:**\n{episode_arc}" if episode_arc else ""
        return f"""You are a professional story editor. Critique the following episode of "Gravedancer to General: Anatomy of a Catastrophe". Be honest, specific, and constructive.

**EPISODE TITLE:** {title}
**NUMBER OF DAYS:** {num_days}
**SETTING / PLANET:** {setting}
**JEDI TARGET:** {json.dumps(jedi_details, ensure_ascii=False, indent=2)}{tone_section}{arc_section}

**EPISODE TEXT:**
{full_story}

Return your critique in this exact format:

For each day, write:
## Day N Critique:
Score: NN/100
**What worked:**
...
**What could be improved:**
...

Then for the whole episode write:
## Overall Episode Critique:
Score: NN/100
**Narrative arc:**
...
**Pacing:**
...
**Thematic coherence:**
...
**Character consistency:**
...
**Key recommendations:**
...
"""

    CRITIQUE_SYSTEM_PROMPT = """You are a ruthless but fair story editor specializing in dark thriller fiction. You evaluate prose for pacing, sensory immersion, character interiority, dialogue quality, tactical plausibility, and thematic resonance. You are specific — you cite examples. You never give a perfect score; there is always room to improve. You write your feedback in clear, direct prose."""

    def parse_critique_report(self, text: str, num_days: int) -> dict[str, Any]:
        """Parse the critique LLM response into structured data."""
        report: dict[str, Any] = {
            "days": [],
            "overall": {
                "score": None,
                "narrative_arc": "",
                "pacing": "",
                "thematic_coherence": "",
                "character_consistency": "",
                "recommendations": "",
            },
        }

        # Parse per-day critiques
        for day_num in range(1, num_days + 1):
            day_pattern = rf"## Day {day_num} Critique:\s*Score:\s*(\d+)/100\s*(.*?)(?=## Day \d+ Critique:|## Overall Episode Critique:|\Z)"
            match = re.search(day_pattern, text, re.DOTALL | re.IGNORECASE)
            if match:
                score = int(match.group(1))
                body = match.group(2).strip()
                worked = ""
                improved = ""
                wm = re.search(r"\*\*What worked:\*\*(.*?)(?=\*\*What could be improved:|$)", body, re.DOTALL)
                if wm:
                    worked = wm.group(1).strip()
                im = re.search(r"\*\*What could be improved:\*\*(.*?)$", body, re.DOTALL)
                if im:
                    improved = im.group(1).strip()
                report["days"].append({
                    "number": day_num,
                    "score": score,
                    "what_worked": worked,
                    "what_could_be_improved": improved,
                })
            else:
                report["days"].append({
                    "number": day_num,
                    "score": None,
                    "what_worked": "",
                    "what_could_be_improved": "",
                })

        # Parse overall critique
        overall_match = re.search(
            r"## Overall Episode Critique:\s*Score:\s*(\d+)/100\s*(.*?)$",
            text, re.DOTALL | re.IGNORECASE,
        )
        if overall_match:
            report["overall"]["score"] = int(overall_match.group(1))
            body = overall_match.group(2).strip()
            for field, key in [
                (r"\*\*Narrative arc:\*\*(.*?)(?=\*\*Pacing:)", "narrative_arc"),
                (r"\*\*Pacing:\*\*(.*?)(?=\*\*Thematic coherence:)", "pacing"),
                (r"\*\*Thematic coherence:\*\*(.*?)(?=\*\*Character consistency:)", "thematic_coherence"),
                (r"\*\*Character consistency:\*\*(.*?)(?=\*\*Key recommendations:)", "character_consistency"),
                (r"\*\*Key recommendations:\*\*(.*?)$", "recommendations"),
            ]:
                m = re.search(field, body, re.DOTALL)
                if m:
                    report["overall"][key] = m.group(1).strip()

        return report

    def critique_story(
        self,
        model: str,
        full_story: str,
        outline: str,
        title: str,
        num_days: int,
        jedi_details: dict[str, str],
        setting: str,
        tone_focus: list[str],
        temperature: float = 0.3,
        system_prompt: str | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        """Run a critique pass on the completed story and return structured feedback."""
        prompt = self.build_critique_prompt(
            full_story=full_story,
            outline=outline,
            title=title,
            num_days=num_days,
            jedi_details=jedi_details,
            setting=setting,
            tone_focus=tone_focus,
        )
        system = system_prompt or self.CRITIQUE_SYSTEM_PROMPT

        if progress_callback:
            progress_callback("critique", "Critiquing episode...")

        LOGGER.info(
            "critique start title=%s days=%s model=%s prompt_chars=%s",
            title, num_days, model, len(prompt),
        )
        result = self.mlx.generate(
            model=model,
            prompt=prompt,
            system=system,
            temperature=temperature,
            max_tokens=4000,
        )
        LOGGER.info("critique end title=%s output_chars=%s", title, len(result))

        report = self.parse_critique_report(result, num_days)
        report["raw"] = result

        if progress_callback:
            progress_callback("critique", "Critique complete.")

        return report
