import unittest
from types import SimpleNamespace

from src.utils.logging_utils import LOG_DIR, LOG_PATH, RUN_LOG_PATH, get_run_log_name, list_log_runs, read_log_tail, start_new_run_log, write_debug_artifact
from src.utils.models import sort_models_for_ui
from src.utils.models import DEFAULT_MODEL
from src.utils.session_state import (
    build_episode_payload,
    build_jedi_details,
    build_prompt_set,
    get_episode_day_prompt_sets,
    get_episode_prompt_sets,
    merge_prompt_sets,
    build_episode_full_json_export,
    get_episode_target_jedi_name,
    render_episode_prompt_archive_summary,
    save_day_prompt_sets,
    summarize_episode_prompt_archive,
    summarize_episode_collection,
    build_story_generation_context,
    build_story_metadata,
    SESSION_DEFAULTS,
    clear_current_episode,
    clear_story_inputs,
    hydrate_story_inputs,
    init_session_state,
)


class _FakeStreamlit:
    def __init__(self):
        self.session_state = {}


class _FakeStorage:
    def __init__(self):
        self.calls = []

    def update_episode(self, **kwargs):
        self.calls.append(kwargs)


class _FakeExpander:
    def __init__(self, st):
        self.st = st

    def __enter__(self):
        self.st.expander_calls.append(self.st.current_expander_label)
        return self.st

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeRenderStreamlit(_FakeStreamlit):
    def __init__(self):
        super().__init__()
        self.expander_calls = []
        self.markdown_calls = []
        self.current_expander_label = ""

    def expander(self, label, expanded=False):
        self.current_expander_label = label
        return _FakeExpander(self)

    def markdown(self, text):
        self.markdown_calls.append(text)


class TestSessionStateHelpers(unittest.TestCase):
    def test_default_model_uses_fast_iteration_model(self):
        self.assertEqual(DEFAULT_MODEL, "mlx-community/gemma-4-e2b-it-qat-OptiQ-4bit")

    def test_log_path_points_to_repo_log_txt(self):
        self.assertTrue(str(LOG_PATH).endswith("log.txt"))

    def test_log_dir_and_run_log_path_exist(self):
        self.assertTrue(LOG_DIR.exists())
        self.assertTrue(str(RUN_LOG_PATH).startswith(str(LOG_DIR)))
        self.assertEqual(RUN_LOG_PATH.name, "Logs_Associated_with_start_of_Run.txt")

    def test_read_log_tail_returns_latest_lines(self):
        tail = read_log_tail(max_lines=3)
        self.assertIsInstance(tail, str)

    def test_write_debug_artifact_writes_repo_file(self):
        artifact = write_debug_artifact("test-debug.txt", "hello")
        self.assertTrue(str(artifact).endswith("test-debug.txt"))
        self.assertTrue(artifact.parent.name.startswith("RUN_"))
        self.assertTrue(artifact.exists())
        self.assertEqual(artifact.read_text(), "hello")
        artifact.unlink(missing_ok=True)

    def test_list_log_runs_returns_recent_entries(self):
        runs = list_log_runs(limit=5)
        self.assertIsInstance(runs, list)
        self.assertLessEqual(len(runs), 5)

    def test_start_new_run_log_switches_run_file(self):
        first = start_new_run_log("unit-test")
        second = start_new_run_log("unit-test")

        self.assertNotEqual(first, second)
        self.assertEqual(first.name, "Logs_Associated_with_start_of_Run.txt")
        self.assertTrue(first.parent.name.startswith("RUN_"))
        self.assertIn("unit-test", first.parent.name)
        self.assertEqual(second.name, "Logs_Associated_with_start_of_Run.txt")

    def test_get_run_log_name_returns_filename(self):
        name = get_run_log_name()
        self.assertEqual(name, "Logs_Associated_with_start_of_Run.txt")

    def test_fast_iteration_model_ranks_in_recommended_order(self):
        installed = [
            "mlx-community/Qwen3.5-4B-4bit",
            "mlx-community/Qwen3.6-27B-4bit",
            "mlx-community/gemma-4-12B-it-OptiQ-4bit",
        ]

        sorted_models = sort_models_for_ui(installed)

        self.assertEqual(sorted_models[0], "mlx-community/Qwen3.6-27B-4bit")
        self.assertEqual(sorted_models[1], "mlx-community/gemma-4-12B-it-OptiQ-4bit")
        self.assertEqual(sorted_models[2], "mlx-community/Qwen3.5-4B-4bit")

    def test_init_session_state_populates_defaults(self):
        fake_st = _FakeStreamlit()

        init_session_state(fake_st)

        for key, value in SESSION_DEFAULTS.items():
            self.assertIn(key, fake_st.session_state)
            self.assertEqual(fake_st.session_state[key], value)

    def test_clear_story_inputs_resets_form_fields(self):
        fake_st = _FakeStreamlit()
        fake_st.session_state.update(
            {
                "story_title": "Title",
                "story_setting": "Kalee",
                "jedi_name": "Target",
                "jedi_species": "Togruta",
                "jedi_rank": "Knight",
                "jedi_saber": "Yellow",
                "jedi_personality": "Stoic",
                "jedi_target": "Blocked a route",
                "story_additional": "More doom",
                "story_tone": ["Action-heavy combat"],
                "story_days": 7,
            }
        )

        clear_story_inputs(fake_st)

        self.assertEqual(fake_st.session_state["story_title"], "")
        self.assertEqual(fake_st.session_state["story_setting"], "")
        self.assertEqual(fake_st.session_state["jedi_name"], "")
        self.assertEqual(fake_st.session_state["story_days"], 5)
        self.assertEqual(fake_st.session_state["story_tone"], [])

    def test_clear_current_episode_resets_episode_state(self):
        fake_st = _FakeStreamlit()
        fake_st.session_state.update(
            {
                "current_story": "Body",
                "current_episode_id": "episode-1",
                "current_metadata": {"title": "Title"},
            }
        )

        clear_current_episode(fake_st)

        self.assertEqual(fake_st.session_state["current_story"], "")
        self.assertIsNone(fake_st.session_state["current_episode_id"])
        self.assertEqual(fake_st.session_state["current_metadata"], {})

    def test_hydrate_story_inputs_copies_concept(self):
        fake_st = _FakeStreamlit()
        concept = {
            "title": "Ash and Bone",
            "days": 4,
            "setting": "Kalee",
            "jedi_name": "Vael Tirin",
            "jedi_species": "Togruta",
            "jedi_rank": "Knight",
            "jedi_saber": "yellow",
            "jedi_personality": "calm",
            "jedi_target": "blocked a route",
            "tone": ["Action-heavy combat"],
        }

        hydrate_story_inputs(fake_st, concept)

        self.assertEqual(fake_st.session_state["story_title"], "Ash and Bone")
        self.assertEqual(fake_st.session_state["story_days"], 4)
        self.assertEqual(fake_st.session_state["jedi_name"], "Vael Tirin")
        self.assertEqual(fake_st.session_state["story_tone"], ["Action-heavy combat"])

    def test_build_story_metadata_uses_session_state(self):
        fake_st = _FakeStreamlit()
        fake_st.session_state.update(
            {
                "story_title": "Ash and Bone",
                "story_days": 4,
                "story_setting": "Kalee",
                "jedi_name": "Vael Tirin",
                "jedi_species": "Togruta",
                "jedi_rank": "Knight",
                "jedi_saber": "yellow",
                "jedi_personality": "calm",
                "jedi_target": "blocked a route",
                "story_tone": ["Action-heavy combat"],
                "story_additional": "Keep it bleak",
            }
        )

        metadata = build_story_metadata(fake_st, model="mock-model", temperature=0.7)

        self.assertEqual(metadata["title"], "Ash and Bone")
        self.assertEqual(metadata["target_jedi_name"], "Vael Tirin")
        self.assertEqual(metadata["tone_focus"], ["Action-heavy combat"])
        self.assertEqual(metadata["model"], "mock-model")
        self.assertEqual(metadata["temperature"], 0.7)

    def test_build_story_generation_context_uses_session_state(self):
        fake_st = _FakeStreamlit()
        fake_st.session_state.update(
            {
                "story_title": "Ash and Bone",
                "story_days": 4,
                "story_setting": "Kalee",
                "jedi_name": "Vael Tirin",
                "jedi_species": "Togruta",
                "jedi_rank": "Knight",
                "jedi_saber": "yellow",
                "jedi_personality": "calm",
                "jedi_target": "blocked a route",
                "story_tone": ["Action-heavy combat"],
                "story_additional": "Keep it bleak",
            }
        )

        context = build_story_generation_context(fake_st)

        self.assertEqual(context["title"], "Ash and Bone")
        self.assertEqual(context["num_days"], 4)
        self.assertEqual(context["setting"], "Kalee")
        self.assertEqual(context["jedi_details"]["name"], "Vael Tirin")
        self.assertEqual(context["tone_focus"], ["Action-heavy combat"])
        self.assertEqual(context["additional_instructions"], "Keep it bleak")

    def test_build_jedi_details_uses_session_state(self):
        fake_st = _FakeStreamlit()
        fake_st.session_state.update(
            {
                "jedi_name": "Vael Tirin",
                "jedi_species": "Togruta",
                "jedi_rank": "Knight",
                "jedi_saber": "yellow",
                "jedi_personality": "calm",
                "jedi_target": "blocked a route",
            }
        )

        jedi_details = build_jedi_details(fake_st)

        self.assertEqual(jedi_details["name"], "Vael Tirin")
        self.assertEqual(jedi_details["species"], "Togruta")
        self.assertEqual(jedi_details["rank"], "Knight")
        self.assertEqual(jedi_details["why_targeted"], "blocked a route")

    def test_build_episode_payload_includes_metadata_context_and_jedi(self):
        fake_st = _FakeStreamlit()
        fake_st.session_state.update(
            {
                "story_title": "Ash and Bone",
                "story_days": 4,
                "story_setting": "Kalee",
                "jedi_name": "Vael Tirin",
                "jedi_species": "Togruta",
                "jedi_rank": "Knight",
                "jedi_saber": "yellow",
                "jedi_personality": "calm",
                "jedi_target": "blocked a route",
                "story_tone": ["Action-heavy combat"],
                "story_additional": "Keep it bleak",
            }
        )

        payload = build_episode_payload(fake_st, model="mock-model", temperature=0.7)

        self.assertEqual(payload["metadata"]["title"], "Ash and Bone")
        self.assertEqual(payload["jedi_details"]["name"], "Vael Tirin")
        self.assertEqual(payload["story_context"]["setting"], "Kalee")

    def test_build_prompt_set_shapes_visual_prompt_payload(self):
        prompt_set = build_prompt_set(
            day_num=3,
            aspect_ratio="21:9",
            new_prompts={
                "wide": "Wide shot",
                "medium": "Medium shot",
                "negative_prompt": "blurry",
                "raw_response": "raw",
            },
        )

        self.assertEqual(prompt_set["day"], 3)
        self.assertEqual(prompt_set["aspect_ratio"], "21:9")
        self.assertEqual(prompt_set["wide"], "Wide shot")
        self.assertEqual(prompt_set["negative_prompt"], "blurry")
        self.assertEqual(prompt_set["prompt_type"], "Flux.2 Klein 4b - DrawThings")

    def test_merge_prompt_sets_appends_and_replaces(self):
        existing_prompts = [
            {"day": 1, "prompt_type": "Flux.2 Klein 4b - DrawThings", "wide": "old"},
            {"day": 2, "prompt_type": "Flux.2 Klein 4b - DrawThings", "wide": "keep"},
        ]
        new_prompts = {"wide": "new", "raw_response": "raw"}

        appended = merge_prompt_sets(existing_prompts, day_num=3, aspect_ratio="16:9", new_prompts=new_prompts)
        replaced = merge_prompt_sets(existing_prompts, day_num=1, aspect_ratio="16:9", new_prompts=new_prompts, replace=True)

        self.assertEqual(len(appended), 3)
        self.assertEqual(appended[-1]["day"], 3)
        self.assertEqual(replaced[0]["day"], 2)
        self.assertEqual(replaced[-1]["day"], 1)
        self.assertEqual(replaced[-1]["wide"], "new")

    def test_save_day_prompt_sets_persists_merged_prompts(self):
        storage = _FakeStorage()
        existing_prompts = [
            {"day": 1, "prompt_type": "Flux.2 Klein 4b - DrawThings", "wide": "old"},
            {"day": 2, "prompt_type": "Flux.2 Klein 4b - DrawThings", "wide": "keep"},
        ]
        new_prompts = {"wide": "new", "raw_response": "raw"}

        prompts = save_day_prompt_sets(
            storage,
            episode_id="episode-1",
            existing_prompts=existing_prompts,
            day_num=2,
            aspect_ratio="16:9",
            new_prompts=new_prompts,
            replace=True,
        )

        self.assertEqual(len(storage.calls), 1)
        self.assertEqual(storage.calls[0]["episode_id"], "episode-1")
        self.assertEqual(storage.calls[0]["prompts"]["aspect_ratio"], "16:9")
        self.assertEqual(len(storage.calls[0]["prompts"]["scenes"]), 2)
        self.assertEqual(prompts[-1]["day"], 2)
        self.assertEqual(prompts[-1]["wide"], "new")

    def test_get_episode_prompt_sets_returns_scenes_list(self):
        episode = {"prompts": {"scenes": [{"day": 1}, {"day": 2}]}}

        prompt_sets = get_episode_prompt_sets(episode)

        self.assertEqual(len(prompt_sets), 2)
        self.assertEqual(prompt_sets[0]["day"], 1)
        self.assertEqual(get_episode_prompt_sets({}), [])

    def test_get_episode_day_prompt_sets_filters_by_day(self):
        episode = {"prompts": {"scenes": [{"day": 1}, {"day": 2}, {"day": 1}]}}

        prompt_sets = get_episode_day_prompt_sets(episode, 1)

        self.assertEqual(len(prompt_sets), 2)
        self.assertTrue(all(p["day"] == 1 for p in prompt_sets))

    def test_get_episode_target_jedi_name_uses_canonical_fallbacks(self):
        self.assertEqual(get_episode_target_jedi_name({"target_jedi_name": "Alpha"}), "Alpha")
        self.assertEqual(get_episode_target_jedi_name({"jedi_name": "Beta"}), "Beta")
        self.assertEqual(get_episode_target_jedi_name({}), "Unknown")

    def test_summarize_episode_prompt_archive_counts_sets_and_days(self):
        episode = {
            "prompts": {
                "scenes": [
                    {"day": 1, "wide": "A"},
                    {"day": 1, "wide": "B"},
                    {"day": 3, "wide": "C"},
                    {"day": None, "wide": "ignored"},
                ]
            }
        }

        summary = summarize_episode_prompt_archive(episode)

        self.assertEqual(summary["prompt_sets"], 4)
        self.assertEqual(summary["prompt_days"], 2)
        self.assertEqual(summary["day_counts"][1], 2)
        self.assertEqual(summary["day_counts"][3], 1)
        self.assertEqual(summary["day_counts"][None], 1)

    def test_render_episode_prompt_archive_summary_uses_shared_helper(self):
        fake_st = _FakeRenderStreamlit()
        episode = {
            "prompts": {
                "scenes": [
                    {"day": 2, "wide": "A"},
                    {"day": 2, "wide": "B"},
                    {"day": 4, "wide": "C"},
                ]
            }
        }

        summary = render_episode_prompt_archive_summary(fake_st, episode, expanded=True)

        self.assertEqual(summary["prompt_sets"], 3)
        self.assertIn("Prompt Set Breakdown", fake_st.expander_calls)
        self.assertTrue(any("**Total saved prompt sets:** 3" in call for call in fake_st.markdown_calls))
        self.assertTrue(any("- Day 2: 2 set(s)" in call for call in fake_st.markdown_calls))
        self.assertTrue(any("- Day 4: 1 set(s)" in call for call in fake_st.markdown_calls))

    def test_render_episode_prompt_archive_summary_handles_empty_prompts(self):
        fake_st = _FakeRenderStreamlit()
        episode = {"prompts": {"scenes": []}}

        summary = render_episode_prompt_archive_summary(fake_st, episode, expanded=False)

        self.assertEqual(summary["prompt_sets"], 0)
        self.assertEqual(summary["prompt_days"], 0)
        self.assertEqual(fake_st.expander_calls, [])
        self.assertEqual(fake_st.markdown_calls, [])

    def test_build_episode_full_json_export_includes_prompt_summary(self):
        episode = {
            "metadata": {"title": "Export Test"},
            "story": "## DAY 1: Dawn\n\nThe hunt begins.",
            "prompts": {
                "scenes": [
                    {"day": 1, "prompt_type": "Flux.2 Klein 4b - DrawThings"},
                    {"day": 1, "prompt_type": "Flux.2 Klein 4b - DrawThings"},
                    {"day": 2, "prompt_type": "Flux.2 Klein 4b - DrawThings"},
                ]
            },
        }

        export_json = build_episode_full_json_export(episode)

        self.assertEqual(export_json["metadata"]["title"], "Export Test")
        self.assertEqual(export_json["prompt_sets"], 3)
        self.assertEqual(export_json["prompt_days"], 2)
        self.assertEqual(export_json["story"], episode["story"])

    def test_build_episode_full_json_export_defaults_prompt_counts_to_zero(self):
        episode = {
            "metadata": {"title": "No Prompt Export"},
            "story": "## DAY 1: Dawn\n\nThe hunt begins.",
        }

        export_json = build_episode_full_json_export(episode)

        self.assertEqual(export_json["metadata"]["title"], "No Prompt Export")
        self.assertEqual(export_json["prompt_sets"], 0)
        self.assertEqual(export_json["prompt_days"], 0)
        self.assertIsNone(export_json["prompts"])

    def test_summarize_episode_collection_counts_dashboard_metrics(self):
        episodes = [
            {
                "num_days": 3,
                "target_jedi_name": "Alpha",
                "prompt_sets": 2,
                "prompt_days": 1,
            },
            {
                "num_days": 5,
                "jedi_name": "Beta",
                "prompt_sets": 0,
                "prompt_days": 0,
            },
            {
                "num_days": 4,
                "target_jedi_name": "Gamma",
                "prompt_sets": 4,
                "prompt_days": 4,
            },
        ]

        summary = summarize_episode_collection(episodes)

        self.assertEqual(summary["total_episodes"], 3)
        self.assertEqual(summary["total_days"], 12)
        self.assertEqual(summary["unique_jedi"], 3)
        self.assertEqual(summary["total_prompt_sets"], 6)
        self.assertEqual(summary["episodes_with_prompts"], 2)
        self.assertEqual(summary["total_prompt_days"], 5)
        self.assertEqual(summary["covered_episodes"], 1)

    def test_summarize_episode_collection_defaults_to_zero_for_empty_list(self):
        summary = summarize_episode_collection([])

        self.assertEqual(summary["total_episodes"], 0)
        self.assertEqual(summary["total_days"], 0)
        self.assertEqual(summary["unique_jedi"], 0)
        self.assertEqual(summary["total_prompt_sets"], 0)
        self.assertEqual(summary["episodes_with_prompts"], 0)
        self.assertEqual(summary["total_prompt_days"], 0)
        self.assertEqual(summary["covered_episodes"], 0)


