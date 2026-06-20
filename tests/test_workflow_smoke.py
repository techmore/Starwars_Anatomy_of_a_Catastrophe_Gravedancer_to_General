import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from src.utils.prompt_generator import PromptGenerator
from src.utils.storage import EpisodeStorage
from src.utils.streaming_ui import STREAM_PANEL_KEYS, build_progress_state, build_stream_runtime, finalize_stream_state, render_cached_outline_banner, render_stream_update, reset_stream_panels
from src.utils.story_generator import StoryGenerator
from src.utils.concepts import build_concept_context_prompt, build_concept_extraction_prompt, try_parse_full_episode_concept, VALID_TONES
from src.utils.prompt_schema import STORY_MULTI_PASS_RULES, STORY_STRUCTURE_REQUIREMENTS, validate_outline_structure, validate_story_prompt_inputs


class TestWorkflowSmoke(unittest.TestCase):
    def test_build_stream_runtime_returns_widgets_and_state(self):
        class _Streamlit:
            def __init__(self):
                self.calls = []

            def empty(self):
                marker = object()
                self.calls.append(marker)
                return marker

        runtime = build_stream_runtime(streamlit_module=_Streamlit())

        self.assertEqual(set(runtime.keys()), {"widgets", "progress_state"})
        self.assertEqual(set(runtime["widgets"].keys()), set(STREAM_PANEL_KEYS))
        self.assertEqual(runtime["progress_state"], {"events": [], "current_stage": "Idle"})

    def test_render_stream_update_uses_friendly_stage_labels(self):
        class _Widget:
            def __init__(self):
                self.calls = []

            def markdown(self, text):
                self.calls.append(text)

        widgets = {key: _Widget() for key in STREAM_PANEL_KEYS}
        progress_state = build_progress_state()

        render_stream_update("day-1-continuity", "Cleaning", "Day prose.", widgets, progress_state)

        self.assertTrue(any("**Current Phase:** Continuity" in call for call in widgets["stage_label"].calls))

    def test_render_stream_update_routes_cached_outline_notice(self):
        class _Widget:
            def __init__(self):
                self.calls = []

            def markdown(self, text):
                self.calls.append(text)

        widgets = {key: _Widget() for key in STREAM_PANEL_KEYS}
        progress_state = build_progress_state()

        render_stream_update("outline", "Resuming from cached outline.", "## DAY 1: Ashfall", widgets, progress_state)

        self.assertTrue(any("Resuming from cached outline" in call for call in widgets["stage_label"].calls))

    def test_render_cached_outline_banner_uses_consistent_copy(self):
        class _Widget:
            def __init__(self):
                self.calls = []

            def markdown(self, text):
                self.calls.append(text)

        widgets = {
            "stage_label": _Widget(),
            "progress_log": _Widget(),
            "outline_live": _Widget(),
        }

        render_cached_outline_banner(widgets, "## DAY 1: Ashfall")

        self.assertTrue(any(call == "**Outline**: Resuming from cached outline." for call in widgets["stage_label"].calls))
        self.assertTrue(any(call == "- **Outline**: Resuming from cached outline." for call in widgets["progress_log"].calls))
        self.assertTrue(any("DAY 1: Ashfall" in call for call in widgets["outline_live"].calls))

    def test_render_stream_update_tolerates_missing_widgets(self):
        progress_state = build_progress_state()

        render_stream_update("outline", "Building", "## DAY 1: Ashfall", {}, progress_state)

        self.assertEqual(progress_state["events"], ["1. **Outline**: Building"])
        self.assertEqual(progress_state["current_stage"], "Outline")

    def test_reset_stream_panels_clears_every_present_widget(self):
        class _Widget:
            def __init__(self):
                self.cleared = 0

            def empty(self):
                self.cleared += 1

        widgets = {key: _Widget() for key in STREAM_PANEL_KEYS}

        progress_state = {"events": ["old"], "current_stage": "Section"}

        reset_stream_panels(widgets, progress_state)

        self.assertTrue(all(widget.cleared == 1 for widget in widgets.values()))
        self.assertEqual(progress_state, {"events": [], "current_stage": "Idle"})

    def test_finalize_stream_state_marks_complete(self):
        class _Widget:
            def __init__(self):
                self.calls = []

            def markdown(self, text):
                self.calls.append(text)

        widgets = {
            "stage_label": _Widget(),
            "progress_log": _Widget(),
        }
        progress_state = {"events": ["1. **Outline**: Building"], "current_stage": "Outline"}

        finalize_stream_state(widgets, progress_state, character_count=12345)

        self.assertEqual(progress_state["current_stage"], "Complete")
        self.assertTrue(any("**Current Phase:** Complete" in call for call in widgets["stage_label"].calls))
        self.assertTrue(any("Generation complete. (12,345 chars)" in call for call in widgets["progress_log"].calls))
        self.assertTrue(any("**Progress Events:** 1" in call for call in widgets["progress_log"].calls))

    def test_finalize_stream_state_preserves_last_content(self):
        class _Widget:
            def __init__(self):
                self.calls = []

            def markdown(self, text):
                self.calls.append(text)

            def empty(self):
                self.calls.append("EMPTY")

        widgets = {key: _Widget() for key in STREAM_PANEL_KEYS}
        progress_state = {"events": ["1. **Outline**: Building"], "current_stage": "Outline"}
        widgets["outline_live"].markdown("#### Live Outline\n```markdown\nOutline content\n```")

        finalize_stream_state(widgets, progress_state, character_count=12345)

        self.assertNotIn("EMPTY", widgets["outline_live"].calls)
        self.assertTrue(any("Outline content" in call for call in widgets["outline_live"].calls))

    def test_render_stream_update_uses_consistent_phase_format(self):
        class _Widget:
            def __init__(self):
                self.calls = []

            def markdown(self, text):
                self.calls.append(text)

        widgets = {
            "stage_label": _Widget(),
            "progress_log": _Widget(),
            "outline_live": _Widget(),
            "day_live": _Widget(),
            "section_live": _Widget(),
        }
        progress_state = build_progress_state()

        render_stream_update("outline", "Building", "## DAY 1: Ashfall", widgets, progress_state)

        self.assertTrue(any("**Current Phase:** Outline - Building" in call for call in widgets["stage_label"].calls))
        self.assertTrue(any("**Current Phase:** Outline" in call for call in widgets["progress_log"].calls))

    def test_generate_story_reports_legacy_single_pass_path(self):
        ollama = Mock()
        ollama.generate.return_value = "## DAY 1: Ashfall\n\nA direct legacy pass."
        story_gen = StoryGenerator(ollama)

        with self.assertLogs("src.utils.story_generator", level="WARNING") as logs:
            story = story_gen.generate_story(
                model="mock-model",
                title="Legacy Path",
                num_days=1,
                jedi_details={
                    "name": "Vael Tirin",
                    "species": "Togruta",
                    "rank": "Knight",
                    "lightsaber_color": "yellow",
                    "personality": "calm and relentless",
                    "why_targeted": "guards an interdiction route",
                },
                setting="Ryloth frontier",
                tone_focus=["dread"],
                additional_instructions="",
                temperature=0.6,
            )

        self.assertIn("## DAY 1:", story)
        self.assertTrue(any("legacy single-pass path" in entry for entry in logs.output))
        self.assertTrue(ollama.generate.called)

    def test_parse_full_episode_concept_accepts_bold_headers(self):
        response = """**TITLE:** The Fracture of Glass and Bone
**DAYS:** 5
**SETTING:** The Silicate Wastes of Jabiim
**JEDI_NAME:** Tarys Vel
**JEDI_SPECIES:** Togruta
**JEDI_RANK:** Jedi Knight
**JEDI_SABER:** yellow
**JEDI_PERSONALITY:** calm and relentless
**JEDI_TARGET:** guards an interdiction route
**TONE:** Dread, Action-heavy combat, Survival horror
"""

        concept, errors = try_parse_full_episode_concept(response)

        self.assertEqual(errors, [])
        self.assertEqual(concept["title"], "The Fracture of Glass and Bone")
        self.assertEqual(concept["days"], 5)
        self.assertEqual(concept["jedi_name"], "Tarys Vel")
        self.assertEqual(concept["setting"], "The Silicate Wastes of Jabiim")

    def test_parse_full_episode_concept_accepts_number_of_days_fallback(self):
        response = """TITLE: The Fracture of Glass and Bone
NUMBER OF DAYS: 4
SETTING: The Silicate Wastes of Jabiim
JEDI_NAME: Tarys Vel
JEDI_SPECIES: Togruta
JEDI_RANK: Jedi Knight
JEDI_SABER: yellow
JEDI_PERSONALITY: calm and relentless
JEDI_TARGET: guards an interdiction route
TONE: Dread, Action-heavy combat, Survival horror
"""

        concept, errors = try_parse_full_episode_concept(response)

        self.assertEqual(errors, [])
        self.assertEqual(concept["days"], 4)
        self.assertEqual(concept["jedi_name"], "Tarys Vel")

    def test_parse_full_episode_concept_accepts_json(self):
        response = """{
  "title": "Ash and Bone on Kalee",
  "days": 5,
  "setting": "Kalee bone deserts",
  "jedi_name": "Vael Tirin",
  "jedi_species": "Togruta",
  "jedi_rank": "Jedi Knight",
  "jedi_saber": "yellow",
  "jedi_personality": "calm, relentless, Form IV duelist",
  "jedi_target": "blocked a supply corridor the Gravedancer needs",
  "tone": ["Action-heavy combat", "Survival horror", "Narrow escapes"]
}"""

        concept, errors = try_parse_full_episode_concept(response)

        self.assertEqual(errors, [])
        self.assertEqual(concept["title"], "Ash and Bone on Kalee")
        self.assertEqual(concept["days"], 5)
        self.assertEqual(concept["jedi_name"], "Vael Tirin")
        self.assertEqual(concept["tone"], ["Action-heavy combat", "Survival horror", "Narrow escapes"])

    def test_shared_story_prompt_fragments_exist(self):
        self.assertTrue(any("Treat this as a structured planning task first" in line for line in STORY_MULTI_PASS_RULES))
        self.assertTrue(any("Clear narrative arc" in line for line in STORY_STRUCTURE_REQUIREMENTS))

    def test_validate_story_prompt_inputs_rejects_missing_title(self):
        errors = validate_story_prompt_inputs(
            title="",
            num_days=5,
            setting="Kalee",
            jedi_details={"name": "Vael Tirin"},
            tone_focus=["dread"],
        )
        self.assertIn("title is required", errors)

    def test_validate_outline_structure_accepts_expected_shape(self):
        outline = """## EPISODE ARC
The hunt unfolds across two days — first contact, then ambush.

## DAY 1: Ashfall
- Purpose: Establish the hunt
- Beat 1: The Gravedancer arrives at a smoking outpost. He reads the signs and realizes the Jedi is close.
- Beat 2: A trap is sprung deliberately. The fight reveals the Jedi's tactics and philosophy.
- Beat 3: Night falls. The Jedi watches from the edge of camp — a silent challenge.
- Ending hook: A signal in the ash.

## DAY 2: Ambush
- Purpose: Escalate the trap into a decisive confrontation
- Beat 1: The chase narrows to a canyon. Qymaen realizes the Jedi is herding him.
- Beat 2: The ambush is sprung. Combat unfolds through ruined structures with tactical depth.
- Beat 3: The Jedi is cornered. A final choice determines whether this ends in death or escape.
- Ending hook: The Jedi turns back."""
        errors = validate_outline_structure(outline, expected_days=2)
        self.assertEqual(errors, [])

    def test_validate_outline_structure_rejects_missing_hooks(self):
        outline = """## EPISODE ARC
A single day hunt.

## DAY 1: Ashfall
- Purpose: Establish the hunt
- Beat 1: The Gravedancer arrives at a smoking outpost with ash falling like snow.
- Beat 2: A trap is discovered in the ruins. Qymaen reads the signs and adjusts.
- Beat 3: The Jedi appears at dusk, watching. A silent challenge is issued."""
        errors = validate_outline_structure(outline, expected_days=1)
        self.assertTrue(any("missing Ending hook" in err for err in errors))

    def test_concept_context_prompt_is_self_contained_prose(self):
        prompt = build_concept_context_prompt(["Alpha", "Beta"])

        self.assertIn("Gravedancer to General", prompt)
        self.assertIn("Alpha, Beta", prompt)
        self.assertIn("Qymaen jai Sheelal", prompt)
        self.assertIn("2-4 paragraphs", prompt)

    def test_concept_context_prompt_without_used_names(self):
        prompt = build_concept_context_prompt([])

        self.assertIn("Gravedancer to General", prompt)
        self.assertNotIn("Avoid Jedi already used", prompt)

    def test_concept_extraction_prompt_includes_concept_text_and_tones(self):
        prompt = build_concept_extraction_prompt("Jedi Vex'arii defends a temple")

        self.assertIn("Jedi Vex'arii defends a temple", prompt)
        self.assertIn("ONLY valid JSON", prompt)
        self.assertIn("Action-heavy combat", prompt)
        self.assertIn("Psychological horror", prompt)
        self.assertIn("jedi_target", prompt)

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

    def test_multi_pass_story_generation_emits_progress_updates(self):
        ollama = Mock()
        ollama.generate_stream.side_effect = [
            iter([
                "## EPISODE ARC\n",
                "The hunt for Jedi Vael Tirin begins on the Ryloth frontier.\n",
                "\n",
                "## DAY 1: Ashfall\n",
                "- Purpose: Establish the hunt\n",
                "- Beat 1: The Gravedancer lands at a smoking outpost. He reads the signs of a recent skirmish and realizes the Jedi is close. Tension builds as ash falls like snow.\n",
                "- Beat 2: Qymaen tracks through the ruins. A flash of movement — a trap. He springs it deliberately to gauge the Jedi's tactics. The fight is brief but revealing.\n",
                "- Beat 3: Night falls. The Jedi appears at the edge of camp — not to attack, but to watch. A silent challenge. Qymaen understands: this hunt will be different.\n",
                "- Ending hook: A lightsaber ignites in the distance — not a threat, an invitation.",
            ]),
            iter(["Day 1 section 1 prose."]),
            iter(["Day 1 section 2 prose."]),
            iter(["Day 1 section 3 prose."]),
            iter(["Day 1 continuity prose."]),
        ]
        story_gen = StoryGenerator(ollama)
        progress_events = []

        story = story_gen.generate_episode_story_multi_pass(
            model="mock-model",
            title="Progress Test",
            num_days=1,
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
            progress_callback=lambda stage, message, text="": progress_events.append((stage, message, text)),
        )

        self.assertIn("## DAY 1:", story)
        self.assertTrue(any(stage == "outline" for stage, _, _ in progress_events))
        self.assertTrue(any(stage == "day" for stage, _, _ in progress_events))
        self.assertTrue(any(stage == "section" for stage, _, _ in progress_events))
        self.assertTrue(any(stage == "continuity" for stage, _, _ in progress_events))
        self.assertTrue(any(text for _, _, text in progress_events))


