"""Visual prompt generation for DrawThings + Flux.2 Klein 4b and Wan 2.2."""

import json
import re
from typing import Dict, Any, List, Optional
from src.prompts.system_prompts import (
    VISUAL_PROMPT_SYSTEM_PROMPT,
    IMAGE_PROMPT_TEMPLATE,
    VIDEO_PROMPT_TEMPLATE,
    NEGATIVE_PROMPT_DEFAULT
)
from src.utils.ollama_client import OllamaClient


class PromptGenerator:
    def __init__(self, ollama_client: OllamaClient):
        self.ollama = ollama_client
    
    def extract_scenes(
        self,
        story: str,
        max_scenes_per_day: int = 2
    ) -> List[Dict[str, Any]]:
        """Extract key scenes from story (heuristic)."""
        scenes = []
        # Split by day headers
        day_pattern = r"## DAY (\d+):\s*([^\n]+)(.*?)(?=## DAY \d+:|$)"
        day_matches = re.findall(day_pattern, story, re.DOTALL | re.IGNORECASE)
        
        for day_num, day_title, day_content in day_matches:
            # Split day content into paragraphs
            paragraphs = [p.strip() for p in day_content.split("\n\n") if p.strip()]
            
            # Score paragraphs by visual potential
            scored_paragraphs = []
            for i, para in enumerate(paragraphs):
                score = self._score_visual_potential(para)
                scored_paragraphs.append((score, i, para))
            
            # Sort by score, take top N
            scored_paragraphs.sort(reverse=True, key=lambda x: x[0])
            
            for score, idx, para in scored_paragraphs[:max_scenes_per_day]:
                if score > 5:  # Only include paragraphs with visual content
                    scenes.append({
                        "day": int(day_num),
                        "paragraph_index": idx,
                        "text": para,
                        "visual_score": score
                    })
        
        return scenes
    
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
        aspect_ratio: str = "16:9"
    ) -> str:
        """Build prompt for image/video generation from a scene."""
        return f"""Generate detailed image and video prompts for this scene from "Gravedancer to General: Anatomy of a Catastrophe":

**SCENE TEXT (Day {day_number}):**
{scene_text}

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
        aspect_ratio: str = "16:9",
        temperature: float = 0.7,
        system_prompt: Optional[str] = None
    ) -> Dict[str, str]:
        """Generate image and video prompts for a scene."""
        prompt = self.build_scene_prompt(scene_text, day_number, aspect_ratio)
        system = system_prompt or VISUAL_PROMPT_SYSTEM_PROMPT
        
        response = self.ollama.generate(
            model=model,
            prompt=prompt,
            system=system,
            temperature=temperature,
            max_tokens=3000
        )
        
        return self._parse_scene_prompts(response, day_number, aspect_ratio)
    
    def _parse_scene_prompts(
        self,
        response: str,
        day_number: int,
        aspect_ratio: str
    ) -> Dict[str, str]:
        """Parse LLM response into structured prompts."""
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