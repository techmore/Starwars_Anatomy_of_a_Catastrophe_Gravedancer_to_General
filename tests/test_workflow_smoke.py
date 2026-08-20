import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from src.utils.prompt_generator import PromptGenerator
from src.utils.storage import EpisodeStorage
from src.utils.streaming_ui import STREAM_PANEL_KEYS, build_progress_state, build_stream_runtime, finalize_stream_state, render_cached_outline_banner, render_stream_update, reset_stream_panels
from src.utils.story_generator import OUTLINE_MAX_TOKENS, SECTION_MAX_TOKENS, GenerationCancelled, StoryGenerator, outline_token_budget
from src.utils.concepts import build_concept_context_prompt, build_concept_extraction_prompt, try_parse_full_episode_concept, VALID_TONES
from src.utils.prompt_schema import STORY_MULTI_PASS_RULES, STORY_STRUCTURE_REQUIREMENTS, validate_outline_quality, validate_outline_structure, validate_story_prompt_inputs
from scripts.run_spec_pilot import PILOT_JEDI_FALLBACK, _complete_visual_variants, _dedupe_concept_text


class TestWorkflowSmoke(unittest.TestCase):
    def test_outline_budget_is_bounded_for_local_pilot_runs(self):
        self.assertLessEqual(OUTLINE_MAX_TOKENS, 5000)
        self.assertGreaterEqual(SECTION_MAX_TOKENS, 4000)

    def test_outline_budget_scales_for_longer_episodes(self):
        self.assertEqual(outline_token_budget(3), OUTLINE_MAX_TOKENS)
        self.assertEqual(outline_token_budget(5), 7000)
        self.assertEqual(outline_token_budget(8), 8000)

    def test_generation_cancellation_sentinel_stops_before_model_request(self):
        story_gen = StoryGenerator(Mock())
        with patch.dict("os.environ", {"GRAVEDANCER_CANCEL_FILE": "/tmp/gravedancer-cancel-sentinel"}):
            with patch("os.path.isfile", return_value=True):
                with self.assertRaises(GenerationCancelled):
                    story_gen.generate_episode_story_multi_pass(
                        model="mock-model",
                        title="Cancelled",
                        num_days=1,
                        jedi_details={"name": "Vael Tirin"},
                        setting="Ryloth frontier",
                        tone_focus=["dread"],
                        additional_instructions="",
                        outline="## EPISODE ARC\nArc\n\n## DAY 1: Ashfall\n- Purpose: Establish the hunt.\n- Chapter 1: Beat 1: A. Beat 2: B. Beat 3: C. Beat 4: D.\n- Chapter 2: Beat 1: A. Beat 2: B. Beat 3: C. Beat 4: D.\n- Chapter 3: Beat 1: A. Beat 2: B. Beat 3: C. Beat 4: D.\n- Chapter 4: Beat 1: A. Beat 2: B. Beat 3: C. Beat 4: D.\n- Chapter 5: Beat 1: A. Beat 2: B. Beat 3: C. Beat 4: D.\n- Ending hook: Continue.",
                    )

    def test_outline_quality_rejects_repeated_beats(self):
        repeated = "\n".join(
            f"- Chapter {chapter}:\n"
            "  - Beat 1: Qymaen enters the chamber.\n"
            "  - Beat 2: The Jedi raises the shield.\n"
            "  - Beat 3: Qymaen attacks the shield.\n"
            "  - Beat 4: Qymaen retreats to the chamber."
            for chapter in range(1, 6)
        )
        outline = f"## EPISODE ARC\nThe hunt changes him.\n\n## DAY 1: Ashfall\n- Purpose: Escalate.\n{repeated}\n- Ending hook: The storm speaks."
        errors = validate_outline_quality(outline, expected_days=1)
        self.assertTrue(any("repeats" in error for error in errors))

    def test_pilot_concept_context_deduplicates_repeated_model_paragraphs(self):
        text = "One paragraph.\n\nOne paragraph.\n\nA distinct paragraph."
        self.assertEqual(_dedupe_concept_text(text), "One paragraph.\n\nA distinct paragraph.")
        self.assertEqual(PILOT_JEDI_FALLBACK["name"], "Sura Venn")

    def test_visual_prompt_recovery_fills_missing_variants(self):
        visual, recovered = _complete_visual_variants(
            {"wide": "existing wide shot"},
            {"text": "Qymaen crosses the flooded refinery floor."},
        )

        self.assertTrue(recovered)
        self.assertEqual(visual["wide"], "existing wide shot")
        self.assertTrue(all(visual.get(key) for key in ("wide", "medium", "closeup", "dramatic", "alternate")))
        self.assertIn("flooded refinery floor", visual["dramatic"])

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
        self.assertEqual(runtime["progress_state"]["events"], [])
        self.assertEqual(runtime["progress_state"]["current_stage"], "Idle")
        self.assertIn("started_at", runtime["progress_state"])
        self.assertEqual(runtime["progress_state"]["chars_generated"], 0)
        self.assertEqual(runtime["progress_state"]["approx_tokens"], 0)
        self.assertEqual(runtime["progress_state"]["target_tokens"], 0)

    def test_render_stream_update_uses_friendly_stage_labels(self):
        class _Widget:
            def __init__(self):
                self.calls = []

            def markdown(self, text):
                self.calls.append(text)

        widgets = {key: _Widget() for key in STREAM_PANEL_KEYS}
        progress_state = build_progress_state()
        progress_state["target_tokens"] = 100

        render_stream_update("day-1-continuity", "Cleaning", "Day prose.", widgets, progress_state)

        self.assertTrue(any("**Current Phase:** Continuity" in call for call in widgets["stage_label"].calls))
        self.assertTrue(any("**Target:**" in call and "**ETA:**" in call for call in widgets["progress_log"].calls))
        self.assertEqual(progress_state["chars_generated"], len("Day prose."))
        self.assertEqual(progress_state["approx_tokens"], 2)

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
        self.assertEqual(progress_state["events"], [])
        self.assertEqual(progress_state["current_stage"], "Idle")
        self.assertEqual(progress_state["chars_generated"], 0)
        self.assertEqual(progress_state["approx_tokens"], 0)
        self.assertIn("started_at", progress_state)

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
- Chapter 1: Beat 1: The Gravedancer arrives at a smoking outpost. He reads the signs and realizes the Jedi is close. Beat 2: A trap is sprung deliberately. Beat 3: The fight reveals the Jedi's tactics and philosophy. Beat 4: Night falls and the Jedi watches from the edge of camp — a silent challenge.
- Chapter 2: Beat 1: The nearest ridge is swept for tracks. Beat 2: Qymaen finds a damaged relay and decodes the route ahead. Beat 3: A droid scout is buried in ash. Beat 4: The terrain confirms the Jedi is baiting him.
- Chapter 3: Beat 1: The camp repositions to higher ground. Beat 2: Qymaen studies the Jedi's choices. Beat 3: The wind shifts and a hidden passage becomes clear. Beat 4: He commits to the chase.
- Chapter 4: Beat 1: A skirmish erupts at the outpost edge. Beat 2: The Jedi tests Qymaen's patience rather than his blade. Beat 3: The exchange ends without victory. Beat 4: Both sides withdraw with new information.
- Chapter 5: Beat 1: The day closes with ash settling over the dead. Beat 2: Qymaen marks the pattern in the dust. Beat 3: The Jedi's signal fades into the distance. Beat 4: A new trail opens.
- Ending hook: A signal in the ash.

## DAY 2: Ambush
- Purpose: Escalate the trap into a decisive confrontation
- Chapter 1: Beat 1: The chase narrows to a canyon. Qymaen realizes the Jedi is herding him. Beat 2: The ambush is sprung. Combat unfolds through ruined structures with tactical depth. Beat 3: The Jedi is cornered. Beat 4: A final choice determines whether this ends in death or escape. Beat 5: The canyon mouth collapses and the path forward becomes one-way.
- Chapter 2: Beat 1: Qymaen climbs the ridge to regain the high ground. Beat 2: The Jedi uses the rockfall as cover. Beat 3: The terrain becomes a weapon. Beat 4: The hunt turns physical and immediate.
- Chapter 3: Beat 1: A wounded droid squad blocks the retreat path. Beat 2: The Jedi exploits the confusion. Beat 3: Qymaen chooses to press forward. Beat 4: The canyon becomes a trap for both of them.
- Chapter 4: Beat 1: The duel breaks into short, brutal exchanges. Beat 2: The Jedi reveals his philosophy. Beat 3: Qymaen answers with tactical cruelty. Beat 4: Neither side yields.
- Chapter 5: Beat 1: The canyon spits the survivors out into open ground. Beat 2: The Jedi escapes by sacrificing position. Beat 3: Qymaen takes a new wound. Beat 4: The next phase of the hunt begins.
- Ending hook: The Jedi turns back."""
        errors = validate_outline_structure(outline, expected_days=2)
        self.assertEqual(errors, [])

    def test_validate_outline_structure_accepts_nested_beats(self):
        chapters = "\n".join(
            f"- Chapter {chapter}:\n"
            "  - Beat 1: Arrival.\n"
            "  - Beat 2: Discovery.\n"
            "  - Beat 3: Reversal.\n"
            "  - Beat 4: Hook."
            for chapter in range(1, 6)
        )
        outline = f"""## EPISODE ARC
The hunt begins.

## DAY 1: Ashfall
- Purpose: Establish the hunt
{chapters}
- Ending hook: A signal in the ash."""

        self.assertEqual(validate_outline_structure(outline, expected_days=1), [])

    def test_validate_outline_structure_rejects_missing_hooks(self):
        outline = """## EPISODE ARC
A single day hunt.

## DAY 1: Ashfall
- Purpose: Establish the hunt
- Chapter 1: Beat 1: The Gravedancer arrives at a smoking outpost with ash falling like snow. Beat 2: A trap is discovered in the ruins. Beat 3: Qymaen reads the signs and adjusts. Beat 4: The Jedi appears at dusk, watching. Beat 5: A silent challenge is issued.
- Chapter 2: Beat 1: The camp tightens its perimeter. Beat 2: Droids scan the perimeter. Beat 3: The outpost holds its breath. Beat 4: The fire goes out.
- Chapter 3: Beat 1: Qymaen probes the terrain. Beat 2: He finds nothing but ash. Beat 3: The silence becomes suspicious. Beat 4: He commits to pursuit.
- Chapter 4: Beat 1: The wind shifts. Beat 2: The Jedi remains unseen. Beat 3: A false trail leads nowhere. Beat 4: The trap feels deliberate.
- Chapter 5: Beat 1: Night closes in. Beat 2: The hunt pauses. Beat 3: The shadow at the edge of the outpost does not move. Beat 4: The final trail goes cold."""
        errors = validate_outline_structure(outline, expected_days=1)
        self.assertTrue(any("missing Ending hook" in err for err in errors))

    def test_validate_outline_structure_rejects_missing_or_misnumbered_days(self):
        errors = validate_outline_structure("## DAY 1: Ashfall\n- Purpose: Setup", expected_days=2)

        self.assertTrue(any("missing DAY 2 header" in err for err in errors))

    def test_parse_days_ignores_embedded_day_headings(self):
        story = "## DAY 1: Ashfall\n\nA chapter mentions ## DAY 2: only in dialogue."

        self.assertEqual(len(StoryGenerator(Mock()).parse_days(story)), 1)

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
                "- Chapter 1: Beat 1: The Gravedancer lands at a smoking outpost. Beat 2: He reads the signs of a recent skirmish and realizes the Jedi is close. Beat 3: Tension builds as ash falls like snow. Beat 4: He moves into the ruins.\n",
                "- Chapter 2: Beat 1: Qymaen tracks through the ruins. Beat 2: A flash of movement — a trap. Beat 3: He springs it deliberately to gauge the Jedi's tactics. Beat 4: The fight is brief but revealing.\n",
                "- Chapter 3: Beat 1: Night falls. Beat 2: The Jedi appears at the edge of camp — not to attack, but to watch. Beat 3: A silent challenge. Beat 4: Qymaen understands: this hunt will be different.\n",
                "- Chapter 4: Beat 1: The droids sweep the perimeter. Beat 2: The outpost burns lower. Beat 3: Qymaen studies the shadow line. Beat 4: The Jedi leaves a signal in the ash.\n",
                "- Chapter 5: Beat 1: Qymaen marks the trail. Beat 2: The camp hardens. Beat 3: He commits to the next ridge. Beat 4: The signal fades, pulling him onward.\n",
                "- Ending hook: A lightsaber ignites in the distance — not a threat, an invitation.",
            ]),
            iter(["Day 1 section 1 prose."]),
            iter(["Day 1 section 2 prose."]),
            iter(["Day 1 section 3 prose."]),
            iter(["Day 1 continuity prose."]),
            iter(["Day 1 section 5 prose."]),
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
        self.assertTrue(any(text for _, _, text in progress_events))
        max_tokens = [call.kwargs["max_tokens"] for call in ollama.generate_stream.call_args_list]
        self.assertIn(OUTLINE_MAX_TOKENS, max_tokens)
        self.assertIn(SECTION_MAX_TOKENS, max_tokens)

    def test_multi_pass_rebuilds_invalid_cached_outline(self):
        ollama = Mock()
        story_gen = StoryGenerator(ollama)
        rebuilt_outline = (
            "## EPISODE ARC\nA recovered arc.\n\n## DAY 1: Ashfall\n"
            "- Purpose: Establish the hunt.\n"
            "- Chapter 1: Beat 1: Arrival. Beat 2: Tracks. Beat 3: Tension. Beat 4: Move.\n"
            "- Chapter 2: Beat 1: Pursuit. Beat 2: Trap. Beat 3: Counter. Beat 4: Escape.\n"
            "- Chapter 3: Beat 1: Contact. Beat 2: Threat. Beat 3: Choice. Beat 4: Retreat.\n"
            "- Chapter 4: Beat 1: Camp. Beat 2: Signal. Beat 3: Watch. Beat 4: Dawn.\n"
            "- Chapter 5: Beat 1: Choice. Beat 2: Departure. Beat 3: Cost. Beat 4: Trail.\n"
            "- Ending hook: The trail continues."
        )
        ollama.generate_stream.side_effect = [[rebuilt_outline]] + [["Recovered prose."]] * 5

        story = story_gen.generate_episode_story_multi_pass(
            model="mock-model",
            title="Cached Outline Test",
            num_days=1,
            jedi_details={"name": "Vael Tirin"},
            setting="Ryloth frontier",
            tone_focus=["dread"],
            additional_instructions="",
            outline="## DAY 1: Missing Arc and Chapters",
        )

        self.assertIn("## DAY 1: Ashfall", story)
        self.assertEqual(ollama.generate_stream.call_count, 6)

    def test_multi_pass_reuses_checkpointed_day_without_model_call(self):
        ollama = Mock()
        story_gen = StoryGenerator(ollama)
        outline = (
            "## EPISODE ARC\nA test arc.\n\n## DAY 1: Ashfall\n"
            "- Purpose: Establish the hunt.\n"
            "- Chapter 1: Beat 1: Arrival. Beat 2: Tracks. Beat 3: Tension. Beat 4: Move.\n"
            "- Chapter 2: Beat 1: Pursuit. Beat 2: Trap. Beat 3: Counter. Beat 4: Escape.\n"
            "- Chapter 3: Beat 1: Contact. Beat 2: Threat. Beat 3: Choice. Beat 4: Retreat.\n"
            "- Chapter 4: Beat 1: Camp. Beat 2: Signal. Beat 3: Watch. Beat 4: Dawn.\n"
            "- Chapter 5: Beat 1: Choice. Beat 2: Departure. Beat 3: Cost. Beat 4: Trail.\n"
            "- Ending hook: The trail continues."
        )
        checkpoint = "## DAY 1: Ashfall\n\nRecovered prose."

        story = story_gen.generate_episode_story_multi_pass(
            model="mock-model",
            title="Resume Test",
            num_days=1,
            jedi_details={"name": "Vael Tirin"},
            setting="Ryloth frontier",
            tone_focus=["dread"],
            additional_instructions="",
            temperature=0.6,
            outline=outline,
            day_drafts={1: checkpoint},
            draft_only=True,
        )

        self.assertEqual(story, checkpoint)
        ollama.generate_stream.assert_not_called()
