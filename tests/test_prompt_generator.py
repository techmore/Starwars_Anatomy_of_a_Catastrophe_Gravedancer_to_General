import unittest
from unittest.mock import Mock

from src.utils.prompt_generator import PromptGenerator
from src.prompts.system_prompts import NEGATIVE_PROMPT_DEFAULT


class TestPromptGenerator(unittest.TestCase):
    def test_parse_scene_prompts_extracts_all_sections(self):
        generator = PromptGenerator(Mock())
        response = """
### IMAGE PROMPTS (Flux.2 Klein 4b - DrawThings)

**1. Wide/Establishing Shot:**
Red dunes under a blood sky, a lone Kaleesh hunter on a ridge.

**2. Medium/Action Shot:**
The hunter charges through ash and sparks with a raised blade.

**3. Close-up/Detail Shot:**
An amber eye behind a bone mask, cracked servos at the jaw.

**4. Dramatic/Low Angle Shot:**
Towering and menacing, framed by lightning and smoke.

**5. Alternate Style:**
Painterly concept art with stark shadows and crimson highlights.

**Negative Prompt:** blurry, distorted, extra limbs

**DrawThings Settings (Flux.2 Klein 4b):**
- Steps: 24
- CFG Scale: 2.5

### VIDEO PROMPT (Wan 2.2 High Noise 6-bit SVDQuant)

**Keyframe:** The hunter stands on the ridge.

**Motion Description:** Slow forward push, cloak billowing, ash swirling.

**Camera:** Tracking dolly in.

**Wan 2.2 Prompt:** A slow cinematic approach through ash and wind.

**DrawThings Wan 2.2 Settings:**
- FPS: 24
- Motion Bucket: 127
"""
        parsed = generator._parse_scene_prompts(response, day_number=3, aspect_ratio="21:9")

        self.assertEqual(parsed["day"], 3)
        self.assertEqual(parsed["aspect_ratio"], "21:9")
        self.assertIn("blood sky", parsed["wide"])
        self.assertIn("raised blade", parsed["medium"])
        self.assertIn("amber eye", parsed["closeup"])
        self.assertIn("menacing", parsed["dramatic"])
        self.assertIn("stark shadows", parsed["alternate"])
        self.assertEqual(parsed["negative_prompt"], "blurry, distorted, extra limbs")
        self.assertIn("Steps: 24", parsed["drawthings_settings"])
        self.assertIn("tracking dolly", parsed["video_camera"].lower())
        self.assertIn("slow cinematic approach", parsed["video_wan_prompt"])

    def test_prompt_generator_logs_scene_flow(self):
        generator = PromptGenerator(Mock())
        story = """
## DAY 1: Arrival

The Gravedancer ignites his blade and charges through the ruins, sparks and ash flying around his mask.
"""

        with self.assertLogs("src.utils.prompt_generator", level="INFO") as logs:
            scenes = generator.extract_scenes(story, max_scenes_per_day=1)
            prompt = generator.build_scene_prompt("A clash in the ash", day_number=1, beat_label="Beat 1", aspect_ratio="16:9")
            parsed = generator._parse_scene_prompts(
                response="""
**1. Wide/Establishing Shot:**
Ash and ruin.

**2. Medium/Action Shot:**
The Gravedancer swings.

**3. Close-up/Detail Shot:**
Bone mask and amber eye.

**4. Dramatic/Low Angle Shot:**
Low angle menace.

**5. Alternate Style:**
Storyboard frame.

**Negative Prompt:** blurry

**DrawThings Settings (Flux.2 Klein 4b):**
- Steps: 24

### VIDEO PROMPT (Wan 2.2 High Noise 6-bit SVDQuant)

**Keyframe:** The hunter stands.

**Motion Description:** Slow push.

**Camera:** Tracking dolly.

**Wan 2.2 Prompt:** A cinematic push through ash.
""",
                day_number=1,
                aspect_ratio="16:9",
            )

        self.assertTrue(scenes)
        self.assertIn("A clash in the ash", prompt)
        self.assertIn("BEAT ANCHOR", prompt)
        self.assertIn("extract_scenes start", "\n".join(logs.output))
        self.assertIn("extract_scenes end", "\n".join(logs.output))
        self.assertIn("build_scene_prompt day=1", "\n".join(logs.output))
        self.assertIn("parse_scene_prompts start", "\n".join(logs.output))
        self.assertIn("parse_scene_prompts end", "\n".join(logs.output))

    def test_extract_scenes_scores_and_limits_paragraphs(self):
        generator = PromptGenerator(Mock())
        story = """
## DAY 1: Arrival

A quiet approach through fog.

The Gravedancer ignites his blade and charges through the ruins, sparks and ash flying around his mask.

The sky burns red above the temple.

## DAY 2: Pursuit

A calm exchange of words.

He advances again, cloak snapping in the storm while the Jedi parries and retreats.
"""
        scenes = generator.extract_scenes(story, max_scenes_per_day=1)

        self.assertEqual(len(scenes), 2)
        self.assertEqual([scene["day"] for scene in scenes], [1, 2])
        self.assertGreaterEqual(scenes[0]["visual_score"], 6)
        self.assertIn("ignites", scenes[0]["text"].lower())
        self.assertIn("advances", scenes[1]["text"].lower())

    def test_default_negative_prompt_is_preserved_when_absent(self):
        generator = PromptGenerator(Mock())
        parsed = generator._parse_scene_prompts(
            response="**1. Wide/Establishing Shot:**\nA ridge line at dawn.",
            day_number=1,
            aspect_ratio="16:9",
        )

        self.assertEqual(parsed["negative_prompt"], NEGATIVE_PROMPT_DEFAULT)


