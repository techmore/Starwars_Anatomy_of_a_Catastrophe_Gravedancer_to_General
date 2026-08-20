"""Visual prompt generation for Draw Things + Flux.2 Klein 4b and Wan 2.2."""

import json
import re
from typing import Dict, Any, List, Optional
import time
from src.prompts.system_prompts import (
    VISUAL_PROMPT_SYSTEM_PROMPT,
    NEGATIVE_PROMPT_DEFAULT
)
from src.utils.logging_utils import get_logger
from src.utils.contracts import TextGenerationBackend


LOGGER = get_logger(__name__)

# Visual prompt output is structured into a small fixed set of sections. A
# bounded response leaves room for the 27B story runtime and Draw Things on a
# 32 GB unified-memory Mac without sacrificing usable prompt detail.
VISUAL_PROMPT_MAX_TOKENS = 1200


class PromptGenerator:
    def __init__(self, mlx_client: TextGenerationBackend):
        self.mlx = mlx_client
    
    def extract_scenes(
        self,
        story: str,
        max_scenes_per_day: int = 2,
        day_number: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Extract key scenes from a full story or an individual day body.

        The library visual pipeline operates on one parsed day at a time, so
        ``day_number`` lets callers retain the correct day when the supplied
        text does not include a ``## DAY`` heading.
        """
        start = time.perf_counter()
        LOGGER.info("extract_scenes start story_chars=%s max_scenes_per_day=%s", len(story or ""), max_scenes_per_day)
        scenes = []
        # Split by day headers
        day_pattern = r"^## DAY (\d+):\s*([^\n]+)(.*?)(?=^## DAY \d+:|\Z)"
        day_matches = re.findall(day_pattern, story, re.DOTALL | re.IGNORECASE | re.MULTILINE)
        if not day_matches and story and day_number is not None:
            day_matches = [(str(day_number), f"Day {day_number}", story)]
        
        for day_num, day_title, day_content in day_matches:
            beat_blocks = self._extract_beat_blocks(day_content)
            if beat_blocks:
                candidates = beat_blocks
            else:
                # Fall back to paragraphs if the story has not been beat-structured yet.
                candidates = [
                    {"label": "", "text": p.strip()}
                    for p in day_content.split("\n\n")
                    if p.strip()
                ]

            # Score paragraphs by visual potential
            scored_paragraphs = []
            for i, candidate in enumerate(candidates):
                text = candidate["text"]
                score = self._score_visual_potential(text)
                if candidate.get("label"):
                    score += 1
                scored_paragraphs.append((score, i, candidate))
            
            # Sort by score, take top N
            scored_paragraphs.sort(reverse=True, key=lambda x: x[0])
            
            for score, idx, candidate in scored_paragraphs[:max_scenes_per_day]:
                if score > 5:  # Only include paragraphs with visual content
                    beat_label = candidate.get("label", "")
                    scene_text = candidate["text"]
                    scenes.append({
                        "day": int(day_num),
                        "paragraph_index": idx,
                        "beat_label": beat_label,
                        "text": scene_text,
                        "display_title": f"Beat: {beat_label}" if beat_label else f"Scene {idx + 1}",
                        "visual_score": score
                    })
        
        LOGGER.info("extract_scenes end scenes=%s elapsed=%.3fs", len(scenes), time.perf_counter() - start)
        return scenes

    def _extract_beat_blocks(self, day_content: str) -> List[Dict[str, str]]:
        """Extract beat-labeled blocks from a day outline or story block."""
        beat_pattern = r"^- Beat\s+(\d+):\s*(.*?)(?=^- Beat\s+\d+:|^- Ending hook:|$)"
        matches = re.findall(beat_pattern, day_content, re.DOTALL | re.IGNORECASE | re.MULTILINE)
        blocks: List[Dict[str, str]] = []
        for beat_num, text in matches:
            clean_text = text.strip()
            if clean_text:
                blocks.append({
                    "label": f"Beat {beat_num}",
                    "text": clean_text,
                })
        return blocks
    
    def _score_visual_potential(self, paragraph: str) -> int:
        """Score paragraph for visual potential (0-20)."""
        score = 0
        lower = paragraph.lower()
        
        # Action keywords
        action_words = ["swing", "strike", "leap", "charge", "advance", "retreat",
                        "dodge", "block", "parry", "lunge", "draw", "ignite",
                        "fire", "shot", "blade", "saber", "spear", "staff"]
        score += sum(2 for w in action_words if w in lower)
        
        # Atmosphere keywords
        atmosphere_words = ["fog", "rain", "snow", "dust", "ash", "smoke", "mist",
                            "shadow", "dark", "light", "glow", "fire", "storm",
                            "sunset", "dawn", "dusk", "night", "temple", "ruin",
                            "desert", "forest", "cave", "cliff", "throne"]
        score += sum(1 for w in atmosphere_words if w in lower)
        
        # Character keywords
        char_words = ["gravedancer", "grievous", "sheelal", "jedi", "mask",
                      "servo", "cybernetic", "armor", "cloak", "cape", "eye",
                      "face", "hand", "arm", "leg"]
        score += sum(1 for w in char_words if w in lower)
        
        # Length bonus
        if len(paragraph) > 200:
            score += 2
        
        return score
    
    def build_scene_prompt(
        self,
        scene_text: str,
        day_number: int,
        beat_label: str = "",
        aspect_ratio: str = "16:9"
    ) -> str:
        """Build prompt for image/video generation from a scene."""
        LOGGER.info(
            "build_scene_prompt day=%s beat_label=%s aspect_ratio=%s scene_chars=%s",
            day_number,
            beat_label,
            aspect_ratio,
            len(scene_text or ""),
        )
        beat_section = f"\n**BEAT ANCHOR:** {beat_label}" if beat_label else ""
        return f"""Generate detailed image and video prompts for this scene from "Gravedancer to General: Anatomy of a Catastrophe":

**SCENE TEXT (Day {day_number}):**
{scene_text}
{beat_section}

**TASK:**
Create production-ready prompts for:
1. DrawThings + Flux.2 Klein 4b (image generation)
2. Wan 2.2 High Noise 6-bit SVDQuant (image-to-video)

**REQUIRED OUTPUT FORMAT:**

### IMAGE PROMPTS (Flux.2 Klein 4b - DrawThings)

**1. Wide/Establishing Shot:**
[Detailed natural language prompt - 50-100 words. Include: environment, scale, atmosphere, lighting, character placement, camera angle, aspect ratio {aspect_ratio}]

**2. Medium/Action Shot:**
[Detailed prompt - 50-100 words. Include: character in motion, combat pose, interaction, depth of field, motion blur, particle effects]

**3. Close-up/Detail Shot:**
[Detailed prompt - 50-100 words. Include: mask, cybernetic details, eyes, weapons, texture, dramatic lighting]

**4. Dramatic/Low Angle Shot:**
[Detailed prompt - 50-100 words. Include: hero/villain pose, power, menace, dramatic perspective, rim lighting, god rays]

**5. Alternate Style:**
[Painterly/concept art/noir variation - 50-100 words]

**Negative Prompt:** [comma-separated tokens to avoid]

**DrawThings Settings (Flux.2 Klein 4b):**
- Model: Flux.2 Klein 4b
- Steps: 20-30
- CFG Scale: 2.0-3.0
- Sampler: Euler a
- Aspect Ratio: {aspect_ratio}

### VIDEO PROMPT (Wan 2.2 High Noise 6-bit SVDQuant)

**Keyframe:** [Describe the keyframe image that would be generated from the Medium/Action prompt]

**Motion Description:** [Detailed motion over 3-5 seconds - camera movement, character motion, environment dynamics, particle effects]

**Camera:** [Specific camera movement - pan, dolly, crane, tracking, orbit, etc.]

**Wan 2.2 Prompt:** [Single paragraph optimized for Wan 2.2]

**DrawThings Wan 2.2 Settings:**
- Model: Wan 2.2 High Noise 6-bit SVDQuant
- FPS: 24
- Steps: 25
- CFG: 7.0
- Motion Bucket: 127 (medium motion)
- Resolution: 480x832 (portrait) or 832x480 (landscape)

Focus on cinematic Star Wars aesthetic. Gravedancer visual: Kaleesh warrior, bone ancestral mask, early cybernetic augmentations, tattered warlord cloak, predatory stance, four arms or enhanced arms. Jedi target: original character with unique design."""
    
    def generate_scene_prompts(
        self,
        scene_text: str,
        day_number: int,
        model: str,
        beat_label: str = "",
        aspect_ratio: str = "16:9",
        temperature: float = 0.7,
        system_prompt: Optional[str] = None
    ) -> Dict[str, str]:
        """Generate image and video prompts for a scene."""
        start = time.perf_counter()
        LOGGER.info(
            "generate_scene_prompts start day=%s model=%s beat_label=%s aspect_ratio=%s temperature=%.2f",
            day_number,
            model,
            beat_label,
            aspect_ratio,
            temperature,
        )
        prompt = self.build_scene_prompt(scene_text, day_number, beat_label=beat_label, aspect_ratio=aspect_ratio)
        system = system_prompt or VISUAL_PROMPT_SYSTEM_PROMPT
        
        response = self.mlx.generate(
            model=model,
            prompt=prompt,
            system=system,
            temperature=temperature,
            max_tokens=VISUAL_PROMPT_MAX_TOKENS
        )
        
        parsed = self._parse_scene_prompts(response, day_number, aspect_ratio)
        LOGGER.info(
            "generate_scene_prompts end day=%s model=%s elapsed=%.3fs response_chars=%s",
            day_number,
            model,
            time.perf_counter() - start,
            len(response or ""),
        )
        return parsed
    
    def _parse_scene_prompts(
        self,
        response: str,
        day_number: int,
        aspect_ratio: str
    ) -> Dict[str, str]:
        """Parse LLM response into structured prompts."""
        LOGGER.info("parse_scene_prompts start day=%s response_chars=%s", day_number, len(response or ""))
        parsed = {
            "day": day_number,
            "aspect_ratio": aspect_ratio,
            "wide": "",
            "medium": "",
            "closeup": "",
            "dramatic": "",
            "alternate": "",
            "negative_prompt": NEGATIVE_PROMPT_DEFAULT,
            "drawthings_settings": "",
            "video_keyframe": "",
            "video_motion": "",
            "video_camera": "",
            "video_wan_prompt": "",
            "video_settings": "",
            "raw_response": response
        }
        
        # Parse image prompts
        patterns = {
            "wide": r"\*\*1\.\s*Wide/Establishing Shot:\*\*\s*(.*?)(?=\*\*2\.|\n###|\Z)",
            "medium": r"\*\*2\.\s*Medium/Action Shot:\*\*\s*(.*?)(?=\*\*3\.|\n###|\Z)",
            "closeup": r"\*\*3\.\s*Close-up/Detail Shot:\*\*\s*(.*?)(?=\*\*4\.|\n###|\Z)",
            "dramatic": r"\*\*4\.\s*Dramatic/Low Angle Shot:\*\*\s*(.*?)(?=\*\*5\.|\n###|\Z)",
            "alternate": r"\*\*5\.\s*Alternate Style:\*\*\s*(.*?)(?=\*\*Negative|\n###|\Z)",
        }
        
        for key, pattern in patterns.items():
            match = re.search(pattern, response, re.DOTALL | re.IGNORECASE)
            if match:
                parsed[key] = match.group(1).strip()
        
        # Parse negative prompt
        neg_match = re.search(r"\*\*Negative Prompt:\*\*\s*(.*?)(?=\n\n|\n###|\Z)", response, re.DOTALL)
        if neg_match:
            parsed["negative_prompt"] = neg_match.group(1).strip()
        
        # Parse DrawThings settings
        settings_match = re.search(r"\*\*DrawThings Settings.*?\*\*\s*(.*?)(?=\n###|\Z)", response, re.DOTALL)
        if settings_match:
            parsed["drawthings_settings"] = settings_match.group(1).strip()
        
        # Parse video prompts
        video_patterns = {
            "video_keyframe": r"\*\*Keyframe:\*\*\s*(.*?)(?=\*\*Motion|\n###|\Z)",
            "video_motion": r"\*\*Motion Description:\*\*\s*(.*?)(?=\*\*Camera|\n###|\Z)",
            "video_camera": r"\*\*Camera:\*\*\s*(.*?)(?=\*\*Wan|\n###|\Z)",
            "video_wan_prompt": r"\*\*Wan 2\.2 Prompt:\*\*\s*(.*?)(?=\*\*DrawThings Wan|\n###|\Z)",
            "video_settings": r"\*\*DrawThings Wan 2\.2 Settings:\*\*\s*(.*?)(?=\n###|\Z)"
        }
        
        for key, pattern in video_patterns.items():
            match = re.search(pattern, response, re.DOTALL | re.IGNORECASE)
            if match:
                parsed[key] = match.group(1).strip()
        
        LOGGER.info(
            "parse_scene_prompts end day=%s wide=%s medium=%s closeup=%s dramatic=%s alternate=%s",
            day_number,
            bool(parsed["wide"]),
            bool(parsed["medium"]),
            bool(parsed["closeup"]),
            bool(parsed["dramatic"]),
            bool(parsed["alternate"]),
        )
        return parsed
    
    def generate_batch_prompts(
        self,
        scenes: List[Dict[str, Any]],
        model: str,
        aspect_ratio: str = "16:9",
        temperature: float = 0.7,
        system_prompt: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """Generate prompts for multiple scenes."""
        results = []
        for i, scene in enumerate(scenes):
            try:
                prompts = self.generate_scene_prompts(
                    scene_text=scene["text"],
                    day_number=scene["day"],
                    beat_label=scene.get("beat_label", ""),
                    model=model,
                    aspect_ratio=aspect_ratio,
                    temperature=temperature,
                    system_prompt=system_prompt
                )
                prompts["scene_text"] = scene["text"]
                prompts["scene_index"] = i
                results.append(prompts)
            except Exception as e:
                results.append({
                    "error": str(e),
                    "scene_text": scene["text"],
                    "scene_index": i
                })
        return results

    def extract_chapters(
        self,
        story: str,
    ) -> List[Dict[str, Any]]:
        """Extract chapter-level sections from each day of a story.

        Returns a list of dicts with keys: day, day_title, chapter_index,
        chapter_title, text.
        """
        chapters = []
        day_pattern = r"^## DAY (\d+):\s*([^\n]+)(.*?)(?=^## DAY \d+:|\Z)"
        for day_num, day_title, day_content in re.findall(day_pattern, story, re.DOTALL | re.IGNORECASE | re.MULTILINE):
            chapter_pattern = r"(?:^|\n)###\s+(?:Chapter\s+)?(\d+)[:\s]*(.*?)(?=\n###|\n## DAY|\Z)"
            chapter_matches = re.findall(chapter_pattern, day_content, re.DOTALL | re.IGNORECASE)
            if not chapter_matches:
                chapters.append({
                    "day": int(day_num),
                    "day_title": day_title.strip(),
                    "chapter_index": 1,
                    "chapter_title": "Full Day",
                    "text": day_content.strip(),
                })
            else:
                for chap_num, chap_title_rest in chapter_matches:
                    rest = chap_title_rest.strip()
                    chap_title = rest.split("\n")[0].strip() if rest else f"Chapter {chap_num}"
                    chap_text = rest[len(chap_title):].strip() if rest else ""
                    chapters.append({
                        "day": int(day_num),
                        "day_title": day_title.strip(),
                        "chapter_index": int(chap_num),
                        "chapter_title": chap_title,
                        "text": chap_text or rest,
                    })
        return chapters

    def build_banner_prompt(self, metadata: Dict[str, Any]) -> str:
        """Build a prompt to generate an episode banner/hero image."""
        title = metadata.get("title", "Untitled")
        setting = metadata.get("setting", "Unknown")
        jedi_name = metadata.get("target_jedi_name") or metadata.get("jedi_name", "Unknown")
        jedi_species = metadata.get("jedi_species", "Unknown")
        jedi_rank = metadata.get("jedi_rank", "Unknown")
        jedi_saber = metadata.get("jedi_lightsaber_color", "Unknown")
        jedi_personality = metadata.get("jedi_personality", "")
        tone = ", ".join(metadata.get("tone_focus", [])) or "Star Wars thriller"
        return f"""Generate a single cinematic banner image prompt for this episode of "Gravedancer to General: Anatomy of a Catastrophe".

**EPISODE TITLE:** {title}
**SETTING:** {setting}
**JEDI TARGET:** {jedi_name} ({jedi_species}, {jedi_rank})
**JEDI SABER:** {jedi_saber}
**JEDI PERSONALITY:** {jedi_personality}
**TONE:** {tone}

**REQUIRED OUTPUT:**
A single clean image prompt only, 80-140 words, no analysis, no bullets, no headings, no notes, no markdown, no internal reasoning.
Include the Gravedancer, the Jedi target, the setting, the tone, and cinematic Star Wars composition in one polished paragraph.
"""

    def generate_banner_prompt(
        self,
        metadata: Dict[str, Any],
        model: str,
        temperature: float = 0.7,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, str]:
        """Generate a banner image prompt for an episode."""
        prompt_text = self.build_banner_prompt(metadata)
        system = system_prompt or VISUAL_PROMPT_SYSTEM_PROMPT
        response = self.mlx.generate(
            model=model,
            prompt=prompt_text,
            system=system,
            temperature=temperature,
            max_tokens=1000,
        )
        banner = self._clean_visual_prompt(response)
        return {
            "banner_prompt": banner,
            "negative_prompt": NEGATIVE_PROMPT_DEFAULT,
            "raw_response": response,
        }

    def _clean_visual_prompt(self, response: str) -> str:
        """Strip prompt-engineering scaffolding and keep only the final usable prompt."""
        text = (response or "").strip()
        if not text:
            return ""

        text = re.sub(r"(?is)<\|channel\|>.*?(?=\*\*IMAGE PROMPT:\*\*|\Z)", "", text).strip()
        text = re.sub(r"(?is)^(?:\*\*IMAGE PROMPT:\*\*|IMAGE PROMPT:)\s*", "", text).strip()
        text = re.sub(r"(?is)^\s*(?:\*\*Final Prompt\*\*|Final Prompt:)\s*", "", text).strip()
        text = re.sub(r"(?is)\*\*Negative Prompt:\*\*.*$", "", text).strip()
        text = re.sub(r"(?is)^<\|.*?\|>\s*", "", text).strip()
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        lines = [line for line in lines if not line.lower().startswith(("thought", "analysis", "review", "drafting", "optimization"))]
        return " ".join(lines).strip().strip('"\'')

    def generate_chapter_prompt(
        self,
        chapter_text: str,
        day_number: int,
        chapter_index: int,
        chapter_title: str,
        model: str,
        aspect_ratio: str = "16:9",
        temperature: float = 0.7,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, str]:
        """Generate a focused prompt set for one chapter."""
        prompt = f"""Generate image prompts for this chapter from "Gravedancer to General: Anatomy of a Catastrophe".

**CHAPTER:** Day {day_number}, Chapter {chapter_index}: {chapter_title}
**ASPECT RATIO:** {aspect_ratio}

**CHAPTER TEXT:**
{chapter_text}

**REQUIRED OUTPUT — exactly 3 shots:**

**1. Establishing Shot:**
[60-80 word prompt — wide view of the chapter's primary scene]

**2. Character / Action Shot:**
[60-80 word prompt — focus on the main character moment or action]

**3. Dramatic / Close-up Shot:**
[60-80 word prompt — detail shot, emotional beat, or dramatic moment]

**Negative Prompt:** [comma-separated tokens]"""
        system = system_prompt or VISUAL_PROMPT_SYSTEM_PROMPT
        response = self.mlx.generate(
            model=model,
            prompt=prompt,
            system=system,
            temperature=temperature,
            max_tokens=2000,
        )
        parsed = {"day": day_number, "chapter": chapter_index, "aspect_ratio": aspect_ratio}
        shot_labels = ("Establishing Shot", "Character / Action Shot", "Dramatic / Close-up Shot")
        for key, label in zip(("wide", "medium", "closeup"), shot_labels):
            # Accept bold, Markdown-heading, numbered, and unnumbered forms.
            heading = rf"(?:\*\*\s*(?:\d+\.\s*)?{re.escape(label)}\s*:\s*\*\*|^\s*#+\s*(?:\d+\.\s*)?{re.escape(label)}\s*:?\s*$)"
            next_heading = "|".join(
                rf"(?:\*\*\s*(?:\d+\.\s*)?{re.escape(other)}\s*:\s*\*\*|^\s*#+\s*(?:\d+\.\s*)?{re.escape(other)}\s*:?\s*$)"
                for other in (*shot_labels, "Negative Prompt")
                if other != label
            )
            m = re.search(rf"{heading}\s*(.*?)(?={next_heading}|\Z)", response, re.DOTALL | re.IGNORECASE | re.MULTILINE)
            if not m:
                # Gemma commonly emits a `### Scene N` wrapper followed by a
                # `#### N. Shot Name (variant)` heading and `**Prompt:**`.
                m = re.search(
                    rf"^\s*#{{2,6}}[ \t]*(?:\d+\.[ \t]*)?{re.escape(label)}(?:[ \t]*\([^\n)]*\))?[ \t]*:?[^\n]*\n+(.*?)(?=^\s*#{{2,6}}\s*(?:Scene\s+\d+|(?:\d+\.\s*)?(?:{'|'.join(map(re.escape, shot_labels))}|Negative Prompt))|\Z)",
                    response,
                    re.DOTALL | re.IGNORECASE | re.MULTILINE,
                )
            parsed[key] = m.group(1).strip() if m else ""
        neg_m = re.search(r"(?:\*\*\s*Negative Prompt\s*:\s*\*\*|^\s*#+\s*Negative Prompt\s*:?\s*$)\s*(.*?)$", response, re.DOTALL | re.IGNORECASE | re.MULTILINE)
        parsed["negative_prompt"] = neg_m.group(1).strip() if neg_m else NEGATIVE_PROMPT_DEFAULT
        parsed["raw_response"] = response
        return parsed
