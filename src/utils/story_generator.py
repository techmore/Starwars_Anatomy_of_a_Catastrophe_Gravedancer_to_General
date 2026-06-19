"""Story generation logic using Ollama."""

from typing import Dict, Any, Optional, List
import re
from src.prompts.system_prompts import STORY_GENERATION_SYSTEM_PROMPT
from src.utils.ollama_client import OllamaClient


class StoryGenerator:
    def __init__(self, ollama_client: OllamaClient):
        self.ollama = ollama_client
    
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
        
        jedi_section = ""
        if jedi_details.get("name"):
            jedi_section = f"""
**JEDI TARGET:**
- Name: {jedi_details.get('name', 'Unknown')}
- Species: {jedi_details.get('species', 'Unknown')}
- Rank: {jedi_details.get('rank', 'Unknown')}
- Lightsaber Color: {jedi_details.get('lightsaber_color', 'Unknown')}
- Personality/Ability: {jedi_details.get('personality', 'Unknown')}
- Why Targeted: {jedi_details.get('why_targeted', 'Unknown')}"""
        
        tone_section = ""
        if tone_focus:
            tone_section = f"""
**TONE / FOCUS:** {", ".join(tone_focus)}"""
        
        additional_section = ""
        if additional_instructions.strip():
            additional_section = f"""
**ADDITIONAL INSTRUCTIONS:**
{additional_instructions}"""
        
        prompt = f"""Write an episode for "Gravedancer to General: Anatomy of a Catastrophe".

**EPISODE TITLE:** {title}
**NUMBER OF DAYS:** {num_days}
**SETTING / PLANET:** {setting}{jedi_section}{tone_section}{additional_section}

Write a complete {num_days}-day novella following the series format. **Target ~7,500 words total** (range 6,500-9,000). Per-day target: ~{7500 // num_days:,} words per day. Each day should have 3-5 distinct scenes.

**NOVELLA STRUCTURE REQUIRED:**
- Clear narrative arc (setup → rising action → climax → resolution/open ending)
- Protagonist transformation arc: Qymaen ends the episode further along the path to Grievous — colder, more cybernetic, more willing to cross lines
- A thematic spine (one core theme: cost of honor, seduction of power, war as ritual, what makes a monster, the last human thing)
- A distinct Jedi antagonist with their own philosophy and a defining moment of choice
- A closing image that lands like a hammer — a single image, decision, or haunting line on the final day

Build dread, action, and character transformation through sensory detail, tactical combat, character interiority, and meaningful dialogue. The outcome on the final day should NOT be predetermined - it could be a kill, a narrow escape, a trap sprung, a psychological victory, a droid engagement, or an ongoing pursuit. End each day on a hook that pulls the reader forward.

Use the writing style described in your system prompt: cinematic, visceral, atmospheric, with internal monologue, sparse dialogue, the hiss of servos, weight of durasteel, hum of lightsabers in rain.

Begin with "## DAY 1:" and continue through "## DAY {num_days}:". """
        return prompt
    
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
        """Generate a complete story."""
        prompt = self.build_prompt(
            title, num_days, jedi_details, setting, tone_focus, additional_instructions
        )
        system = system_prompt or STORY_GENERATION_SYSTEM_PROMPT
        
        # Sized for ~7,500 word novella target (~1.3 tokens per word)
        # Allow comfortable headroom: 3 days = 12k, 5 days = 14k, 8 days = 18k
        max_tokens = max(10000, 8000 + num_days * 1200)
        
        return self.ollama.generate(
            model=model,
            prompt=prompt,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens
        )
    
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
        
        # Sized for ~7,500 word novella target
        max_tokens = max(10000, 8000 + num_days * 1200)
        
        yield from self.ollama.generate_stream(
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

Write a NEW Day {day_number} with a descriptive title. **Target: ~{7500 // num_days:,} words of full immersive prose** (3-5 scenes per day). Maintain continuity with previous/next days. Same quality, sensory depth, character interiority, tactical detail, and thematic resonance. The day should advance the novella's transformation arc and thematic spine. Focus on: {', '.join(tone_focus) if tone_focus else 'action and dread'}."""
        
        system = system_prompt or STORY_GENERATION_SYSTEM_PROMPT
        
        # Allow ~1.5x word target in tokens for a single day
        day_target_tokens = int((7500 // num_days) * 1.5)
        new_day = self.ollama.generate(
            model=model,
            prompt=regen_prompt,
            system=system,
            temperature=temperature,
            max_tokens=max(3000, day_target_tokens)
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