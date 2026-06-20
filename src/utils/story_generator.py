"""Story generation logic using MLX."""

from typing import Dict, Any, Optional, List
import json
import re
import time
from src.prompts.system_prompts import STORY_GENERATION_SYSTEM_PROMPT
from src.utils.prompt_schema import (
    STORY_CONTINUITY_HEADER,
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
from src.utils.logging_utils import get_logger
from src.utils.mlx_client import MLXClient


LOGGER = get_logger(__name__)


class StoryGenerator:
    def __init__(self, mlx_client: MLXClient):
        self.mlx = mlx_client
    
    def build_prompt(
        self,
        title: str,
        num_days: int,
        jedi_details: Dict[str, str],
        setting: str,
        tone_focus: List[str],
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
        jedi_details: Dict[str, str],
        setting: str,
        tone_focus: List[str],
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
- Beat 1: [2-4 sentences describing what happens, the tension point, and the micro-hook that drives into Beat 2]
- Beat 2: [2-4 sentences]
- Beat 3: [2-4 sentences]
- (Beat 4, Beat 5 optional — 3 to 5 beats per day)
- Ending hook: [1-2 sentences — what pulls the reader into the next day]

Rules:
- Each day must have 3 to 5 beats. Each beat must be 2-4 sentences of concrete scene guidance — NOT a one-liner. Describe what happens, why it matters, and what tension it creates.
- The beats should be specific enough that a later expansion pass can write prose from them without inventing new plot turns.
- Treat each day as a self-contained thriller chapter with its own escalation arc.
- Keep the overall episode arc coherent across all days.
- Preserve continuity of locations, injuries, emotional state, and Jedi capabilities.
- Use the beats to stage the day's internal rhythm: setup, pressure, escalation, reversal, hook.
- Keep Day 1 setup strong and the final day decisive.
- The Jedi target DIES on the final day unless the tone explicitly says 'Ongoing pursuit (no kill)'.
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
        jedi_details: Dict[str, str],
        setting: str,
        tone_focus: List[str],
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
- Write approximately 7,500 words for this day (roughly 30-40 paragraphs).
- Expand each beat into a distinct scene sequence.
- Keep the beats from the outline in order.
- Turn each beat into a small cause-and-effect micro-sequence instead of a vague mood paragraph.
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
        jedi_details: Dict[str, str],
        setting: str,
        tone_focus: List[str],
        additional_instructions: str,
    ) -> str:
        """Build a focused prompt to expand one section outline into prose."""
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
        episode_arc = self.parse_episode_arc(outline)
        arc_section = f"\n**EPISODE ARC:**\n{episode_arc}" if episode_arc else ""
        section_word_target = TARGET_WORDS_PER_DAY // max(section_count, 1)
        return f"""{STORY_SECTION_EXPANSION_HEADER.format(section_index=section_index, day_number=day_number)}

**EPISODE TITLE:** {title}
**TOTAL DAYS:** {num_days}
**SETTING / PLANET:** {setting}
**JEDI TARGET:** {json.dumps(jedi_details, ensure_ascii=False, indent=2)}
{tone_section}{additional_section}
{arc_section}

**SECTION {section_index} OUTLINE:**
{section_outline}
{prior_section}

Write only the prose for this section. Requirements:
- Continue the story seamlessly from the prior prose.
- Keep this section focused on the provided outline.
- Do not invent a new major beat.
- Write vivid, cinematic prose with thriller pacing.
- Preserve names, injuries, object locations, and emotional state.
- Write approximately {section_word_target:,} words for this section.
- Structure the section as a compact chapter with 2-4 micro-beat-sized movements.
"""

    def build_continuity_prompt(self, outline: str, day_text: str, day_number: int) -> str:
        """Build a light continuity cleanup prompt for a finished day."""
        return f"""{STORY_CONTINUITY_HEADER.format(day_number=day_number)} Keep the story's meaning, tone, and structure intact. Do not summarize; output the revised prose only.

**OUTLINE:**
{outline}

**DAY {day_number} PROSE:**
{day_text}
"""

    def regenerate_day_from_draft(
        self,
        model: str,
        day_number: int,
        day_draft: str,
        outline: str,
        title: str,
        num_days: int,
        jedi_details: Dict[str, str],
        setting: str,
        tone_focus: List[str],
        additional_instructions: str,
        previous_day: str = "",
        temperature: float = 0.8,
        system_prompt: Optional[str] = None,
    ) -> str:
        """Regenerate a single day using the assembled draft as the source input."""
        prompt = self.build_day_expansion_prompt(
            title=title,
            num_days=num_days,
            outline=outline,
            day_number=day_number,
            day_outline=day_draft,
            day_draft=day_draft,
            previous_day=previous_day,
            jedi_details=jedi_details,
            setting=setting,
            tone_focus=tone_focus,
            additional_instructions=additional_instructions,
        )
        return self.mlx.generate(
            model=model,
            prompt=prompt,
            system=system_prompt or STORY_GENERATION_SYSTEM_PROMPT,
            temperature=temperature,
            max_tokens=max(8000, 11000),
        )
    
    def generate_story(
        self,
        model: str,
        title: str,
        num_days: int,
        jedi_details: Dict[str, str],
        setting: str,
        tone_focus: List[str],
        additional_instructions: str,
        temperature: float = 0.8,
        system_prompt: Optional[str] = None
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
        
        # Sized for a much longer per-day target (~7,500 words/day).
        # Keep generous headroom so the model can breathe without truncation.
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
        jedi_details: Dict[str, str],
        setting: str,
        tone_focus: List[str],
        additional_instructions: str,
        temperature: float = 0.5,
        system_prompt: Optional[str] = None,
        progress_callback: Optional[callable] = None,
    ) -> str:
        prompt = self.build_outline_prompt(title, num_days, jedi_details, setting, tone_focus, additional_instructions)
        system = system_prompt or STORY_GENERATION_SYSTEM_PROMPT
        max_tokens = 2500
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
            chunks: List[str] = []
            collected = ""
            for chunk in self.mlx.generate_stream(
                model=model, prompt=prompt, system=system,
                temperature=temperature, max_tokens=max_tokens,
            ):
                chunks.append(chunk)
                collected += chunk
                progress_callback(stage="outline", message="Building episode outline...", text=collected)
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
        jedi_details: Dict[str, str],
        setting: str,
        tone_focus: List[str],
        additional_instructions: str,
        temperature: float = 0.8,
        system_prompt: Optional[str] = None,
        outline: Optional[str] = None,
        day_drafts: Optional[Dict[int, str]] = None,
        draft_only: bool = False,
        progress_callback: Optional[Any] = None,
    ) -> str:
        """Generate outline first, then expand each day."""
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
            system_prompt: Optional[str],
            temperature: float,
            max_tokens: int,
        ) -> str:
            _emit(stage, message)
            chunks: List[str] = []
            collected = ""
            for chunk in self.mlx.generate_stream(
                model=model,
                prompt=prompt,
                system=system_prompt or STORY_GENERATION_SYSTEM_PROMPT,
                temperature=temperature,
                max_tokens=max_tokens,
            ):
                chunks.append(chunk)
                collected += chunk
                _emit(stage, message, collected)
            return "".join(chunks)

        if not outline:
            outline_start = time.perf_counter()
            LOGGER.info(
                "outline pass begin title=%s days=%s model=%s temperature=%.2f max_tokens=%s",
                title,
                num_days,
                model,
                max(0.2, temperature - 0.2),
                2500,
            )
            outline = _stream_generate(
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
                max_tokens=4000,
            )
            outline_errors = validate_outline_structure(outline, expected_days=num_days)
            if outline_errors:
                raise ValueError(f"Invalid outline structure: {', '.join(outline_errors)}")
            LOGGER.info("outline pass end title=%s chars=%s elapsed=%.3fs", title, len(outline), time.perf_counter() - outline_start)
            _emit("outline", f"Outline ready ({len(outline):,} chars).")
        day_blocks = self._split_outline_days(outline)
        day_stories: List[str] = []
        previous_day = ""
        for day_number in range(1, num_days + 1):
            day_outline = day_blocks.get(day_number, "")
            day_draft = (day_drafts or {}).get(day_number, "")
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
                _emit("section", f"Using assembled draft for Day {day_number}.")
                LOGGER.info("day draft mode begin title=%s day=%s draft_chars=%s", title, day_number, len(day_draft))
                day_text = _stream_generate(
                    stage=f"day-{day_number}",
                    message=f"Streaming Day {day_number} draft...",
                    model=model,
                    prompt=self.build_day_expansion_prompt(
                        title=title,
                        num_days=num_days,
                        outline=outline,
                        day_number=day_number,
                        day_outline=day_outline,
                        day_draft=day_draft,
                        previous_day=previous_day,
                        jedi_details=jedi_details,
                        setting=setting,
                        tone_focus=tone_focus,
                        additional_instructions=additional_instructions,
                    ),
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=14000,
                )
                LOGGER.info("day draft mode end title=%s day=%s elapsed=%.3fs output_chars=%s", title, day_number, time.perf_counter() - day_start, len(day_text))
            else:
                section_blocks = self._split_day_sections(day_outline)
                section_texts: List[str] = []
                prior_text = previous_day
                LOGGER.info("day section loop begin title=%s day=%s section_count=%s", title, day_number, len(section_blocks))
                for section_index, section_outline in enumerate(section_blocks, start=1):
                    _emit("section", f"Day {day_number}: expanding section {section_index}/{len(section_blocks)}")
                    section_start = time.perf_counter()
                    LOGGER.info(
                        "section pass begin title=%s day=%s section=%s/%s section_chars=%s prior_chars=%s",
                        title,
                        day_number,
                        section_index,
                        len(section_blocks),
                        len(section_outline),
                        len(prior_text),
                    )
                    section_prompt = self.build_section_expansion_prompt(
                        title=title,
                        num_days=num_days,
                        outline=outline,
                        day_number=day_number,
                        section_index=section_index,
                        section_count=len(section_blocks),
                        section_outline=section_outline,
                        prior_text=prior_text,
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
                        max_tokens=6000,
                    )
                    section_texts.append(section_text.strip())
                    prior_text = section_text.strip()
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
                _emit("continuity", f"Cleaning continuity for Day {day_number}...")
                LOGGER.info(
                    "continuity pass begin title=%s day=%s section_output_chars=%s",
                    title,
                    day_number,
                    sum(len(part) for part in section_texts),
                )
                continuity_start = time.perf_counter()
                day_text = _stream_generate(
                    stage=f"day-{day_number}-continuity",
                    message=f"Streaming Day {day_number} continuity pass...",
                    model=model,
                    prompt=self.build_continuity_prompt(outline, "\n\n".join(section_texts), day_number),
                    system_prompt=system_prompt,
                    temperature=max(0.2, temperature - 0.1),
                    max_tokens=max(6000, len("\n\n".join(section_texts)) // 3 + 1000),
                )
                LOGGER.info(
                    "continuity pass end title=%s day=%s elapsed=%.3fs output_chars=%s",
                    title,
                    day_number,
                    time.perf_counter() - continuity_start,
                    len(day_text),
                )
            if not day_text.lstrip().startswith(f"## DAY {day_number}:"):
                day_title = self._extract_day_title(day_outline, day_number)
                day_text = f"## DAY {day_number}: {day_title}\n\n{day_text.strip()}"
            day_stories.append(day_text.strip())
            previous_day = day_text.strip()
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

    def _split_outline_days(self, outline: str) -> Dict[int, str]:
        blocks: Dict[int, str] = {}
        pattern = r"(## DAY (\d+):.*?)(?=## DAY \d+:|$)"
        for block, day_num in re.findall(pattern, outline, re.DOTALL | re.IGNORECASE):
            blocks[int(day_num)] = block.strip()
        return blocks

    def _split_day_sections(self, day_outline: str) -> List[str]:
        """Extract section outline lines from a day outline block."""
        lines = [line.strip() for line in day_outline.splitlines() if line.strip()]
        sections: List[str] = []
        capture = False
        for line in lines:
            stripped = line.lstrip("- \t")
            lower = stripped.lower()
            if lower.startswith("beat "):
                capture = True
                sections.append(stripped)
            elif capture and not lower.startswith("ending hook") and not lower.startswith("purpose"):
                sections[-1] += f" {stripped}"
            elif lower.startswith("ending hook"):
                pass
        if not sections and day_outline.strip():
            sections = [day_outline.strip()]
        return sections

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

    def parse_outline_days(self, outline: str) -> List[Dict[str, Any]]:
        """Parse an outline into day blocks and section outlines."""
        days: List[Dict[str, Any]] = []
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

    def _parse_day_sections(self, lines: List[str]) -> List[Dict[str, str]]:
        """Parse section lines into editable section outline blocks."""
        sections: List[Dict[str, str]] = []
        current: Optional[Dict[str, str]] = None
        for line in lines:
            lower = line.lower()
            if lower.startswith("- beat"):
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
    
    def generate_story_stream(
        self,
        model: str,
        title: str,
        num_days: int,
        jedi_details: Dict[str, str],
        setting: str,
        tone_focus: List[str],
        additional_instructions: str,
        temperature: float = 0.8,
        system_prompt: Optional[str] = None
    ):
        """Generate story with streaming."""
        prompt = self.build_prompt(
            title, num_days, jedi_details, setting, tone_focus, additional_instructions
        )
        system = system_prompt or STORY_GENERATION_SYSTEM_PROMPT
        
        # Sized for a much longer per-day target (~7,500 words/day).
        max_tokens = max(12000, num_days * 11000)
        
        LOGGER.info("story stream title=%s days=%s model=%s max_tokens=%s", title, num_days, model, max_tokens)
        yield from self.mlx.generate_stream(
            model=model,
            prompt=prompt,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens
        )
    
    def regenerate_day(
        self,
        model: str,
        day_number: int,
        full_story: str,
        title: str,
        num_days: int,
        jedi_details: Dict[str, str],
        setting: str,
        tone_focus: List[str],
        additional_instructions: str,
        temperature: float = 0.8,
        system_prompt: Optional[str] = None
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
    
    def parse_days(self, story: str) -> List[Dict[str, str]]:
        """Parse story into day sections."""
        days = []
        pattern = r"## DAY (\d+):\s*(.*?)(?=## DAY \d+:|$)"
        matches = re.findall(pattern, story, re.DOTALL | re.IGNORECASE)
        
        for day_num, content in matches:
            # Extract title from first line
            lines = content.strip().split("\n")
            title = lines[0].strip() if lines else f"Day {day_num}"
            days.append({
                "number": int(day_num),
                "title": title,
                "content": content.strip()
            })
        
        return days
    
    def get_stats(self, story: str) -> Dict[str, Any]:
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
        jedi_details: Dict[str, str],
        setting: str,
        tone_focus: List[str],
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

    def parse_critique_report(self, text: str, num_days: int) -> Dict[str, Any]:
        """Parse the critique LLM response into structured data."""
        report: Dict[str, Any] = {
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
        jedi_details: Dict[str, str],
        setting: str,
        tone_focus: List[str],
        temperature: float = 0.3,
        system_prompt: Optional[str] = None,
        progress_callback: Optional[Any] = None,
    ) -> Dict[str, Any]:
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
