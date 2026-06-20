import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from src.utils.prompt_generator import PromptGenerator
from src.utils.storage import EpisodeStorage
from src.utils.story_generator import StoryGenerator


class TestWorkflowSmoke(unittest.TestCase):
    def test_local_episode_workflow_smoke(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ollama = Mock()
            ollama.generate.side_effect = [
                """## DAY 1: Arrival

The Gravedancer crossed the ash flats beneath a blood-red sky.

## DAY 2: Ambush

He ignited his blade and drove the Jedi into the ruin fields.""",
                """### IMAGE PROMPTS (Flux.2 Klein 4b - DrawThings)

**1. Wide/Establishing Shot:**
Ash flats beneath a blood-red sky, the Gravedancer approaching a ruined battlefield.

**2. Medium/Action Shot:**
The Gravedancer ignites his blade and charges through ash and sparks.

**3. Close-up/Detail Shot:**
An amber eye behind a bone mask, servos flexing at the jaw.

**4. Dramatic/Low Angle Shot:**
Low angle menace, cloak snapping in the storm, blade raised.

**5. Alternate Style:**
Storyboard frame with harsh contrast and crimson atmosphere.

**Negative Prompt:** blurry, distorted

**DrawThings Settings (Flux.2 Klein 4b):**
- Steps: 24

### VIDEO PROMPT (Wan 2.2 High Noise 6-bit SVDQuant)

**Keyframe:** The Gravedancer on the ash flats.

**Motion Description:** Slow push in as ash swirls around him.

**Camera:** Tracking dolly.

**Wan 2.2 Prompt:** A cinematic push through ash and wind toward the masked Kaleesh warlord.

**DrawThings Wan 2.2 Settings:**
- FPS: 24
""",
            ]

            story_gen = StoryGenerator(ollama)
            prompt_gen = PromptGenerator(ollama)
            storage = EpisodeStorage(tmpdir)

            story = story_gen.generate_story(
                model="mock-model",
                title="Smoke Test",
                num_days=2,
                jedi_details={
                    "name": "Vael Tirin",
                    "species": "Togruta",
                    "rank": "Knight",
                    "lightsaber_color": "yellow",
                    "personality": "calm and relentless",
                    "why_targeted": "guards an interdiction route",
                },
                setting="Ryloth frontier",
                tone_focus=["dread", "momentum"],
                additional_instructions="Keep the finale unresolved.",
                temperature=0.6,
            )

            self.assertIn("## DAY 1:", story)
            self.assertIn("## DAY 2:", story)

            episode_id = storage.save_episode(
                title="Smoke Test",
                story=story,
                metadata={
                    "title": "Smoke Test",
                    "num_days": 2,
                    "target_jedi_name": "Vael Tirin",
                    "setting": "Ryloth frontier",
                },
            )

            loaded = storage.load_episode(episode_id)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["metadata"]["target_jedi_name"], "Vael Tirin")

            scenes = prompt_gen.extract_scenes(loaded["story"], max_scenes_per_day=1)
            self.assertGreaterEqual(len(scenes), 1)
            self.assertIn(scenes[0]["day"], {1, 2})

            prompts = prompt_gen.generate_scene_prompts(
                scene_text=scenes[0]["text"],
                day_number=scenes[0]["day"],
                model="mock-model",
                aspect_ratio="16:9",
                temperature=0.7,
            )
            self.assertIn("ash flats", prompts["wide"].lower())
            self.assertIn("tracking dolly", prompts["video_camera"].lower())

            bundle = storage.export_episode_bundle(episode_id)
            self.assertIsNotNone(bundle)
            self.assertIn("manifest", bundle)
            self.assertTrue(Path(bundle["files"]["story_md"]).exists())

            archive_bytes = storage.build_episode_archive_bytes(episode_id)
            self.assertIsNotNone(archive_bytes)


if __name__ == "__main__":
    unittest.main()
