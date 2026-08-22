"""Tests for underlength section continuation enforcement."""

import unittest
from unittest.mock import Mock, patch

from src.utils import story_generator as story_generator_module
from src.utils.story_generator import (
    SECTION_CONTINUE_ATTEMPTS,
    SECTION_MIN_WORD_RATIO,
    StoryGenerator,
)

OUTLINE = (
    "## EPISODE ARC\nA single-day arc.\n\n## DAY 1: Ashfall\n"
    "- Purpose: Establish the hunt.\n"
    "- Chapter 1: Beat 1: Arrival. Beat 2: Tracks. Beat 3: Tension. Beat 4: Move.\n"
    "- Chapter 2: Beat 1: Pursuit. Beat 2: Trap. Beat 3: Counter. Beat 4: Escape.\n"
    "- Chapter 3: Beat 1: Contact. Beat 2: Threat. Beat 3: Choice. Beat 4: Retreat.\n"
    "- Chapter 4: Beat 1: Camp. Beat 2: Signal. Beat 3: Watch. Beat 4: Dawn.\n"
    "- Chapter 5: Beat 1: Choice. Beat 2: Departure. Beat 3: Cost. Beat 4: Trail.\n"
    "- Ending hook: The trail continues."
)


class TestSectionContinuation(unittest.TestCase):
    def _make_gen(self, responses: list[str], extra_sections: int = 4):
        ollama = Mock()
        # Outline call first, then one response per section; the tested
        # section (chapter 1) is `responses[0]`, later chapters use filler
        # long enough to avoid triggering their own continuations.
        from src.utils.prompt_schema import TARGET_WORDS_PER_DAY
        filler = ("Continuation prose. " * int(TARGET_WORDS_PER_DAY)).strip()
        scripted = [responses[0]] + [text for text in responses[1:]]
        calls = []
        def side_effect(**kwargs):
            idx = len(calls)  # outline is passed in, so first call is section 1
            calls.append(kwargs)
            if idx < len(scripted):
                return iter(scripted[idx])
            return iter(filler)
        ollama.generate_stream.side_effect = side_effect
        return StoryGenerator(ollama), ollama, calls

    def test_short_section_triggers_continuation(self):
        short = "One terse paragraph."
        story_gen, ollama, calls = self._make_gen([short])
        with patch.object(story_generator_module, "_story_so_far_enabled", return_value=False):
            story = story_gen.generate_episode_story_multi_pass(
                model="m",
                title="T",
                num_days=1,
                jedi_details={"name": "J"},
                setting="S",
                tone_focus=["dread"],
                additional_instructions="",
                outline=OUTLINE,
            )
        prompts = [c["prompt"] for c in calls]
        cont_prompts = [p for p in prompts if "stopped too early" in p]
        self.assertEqual(len(cont_prompts), 1)
        self.assertIn(short.strip(), cont_prompts[0])
        self.assertIn("## DAY 1:", story)
        self.assertIn("Continuation prose.", story)

    def test_long_enough_section_skips_continuation(self):
        # Build a response that already exceeds min ratio of target.
        from src.utils.prompt_schema import TARGET_WORDS_PER_DAY
        big = ("Word " * (int(TARGET_WORDS_PER_DAY * SECTION_MIN_WORD_RATIO) + 10)).strip()
        story_gen, ollama, calls = self._make_gen([big])
        with patch.object(story_generator_module, "_story_so_far_enabled", return_value=False):
            story_gen.generate_episode_story_multi_pass(
                model="m",
                title="T",
                num_days=1,
                jedi_details={"name": "J"},
                setting="S",
                tone_focus=["dread"],
                additional_instructions="",
                outline=OUTLINE,
            )
        prompts = [c["prompt"] for c in calls]
        self.assertFalse(any("stopped too early" in p for p in prompts))

    def test_continuation_attempts_are_bounded(self):
        self.assertGreaterEqual(SECTION_CONTINUE_ATTEMPTS, 1)
        self.assertLess(SECTION_MIN_WORD_RATIO, 1.0)

    def test_continuation_prompt_includes_remaining_budget(self):
        gen = StoryGenerator(Mock())
        prompt = gen.build_section_continuation_prompt(
            day_number=2,
            section_index=3,
            section_text="Existing prose.",
            word_target=6900,
            current_words=900,
            section_outline="- Chapter 3: beats here.",
        )
        self.assertIn("Section 3 of Day 2 stopped too early", prompt)
        self.assertIn("6,000 more words", prompt)
        self.assertIn("Existing prose.", prompt)
        self.assertIn("- Chapter 3: beats here.", prompt)


if __name__ == "__main__":
    unittest.main()
