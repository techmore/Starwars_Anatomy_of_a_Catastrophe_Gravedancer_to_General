import unittest
from types import SimpleNamespace

from src.utils.session_state import (
    build_episode_payload,
    build_jedi_details,
    build_prompt_set,
    get_episode_day_prompt_sets,
    get_episode_prompt_sets,
    merge_prompt_sets,
    save_day_prompt_sets,
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


class TestSessionStateHelpers(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
