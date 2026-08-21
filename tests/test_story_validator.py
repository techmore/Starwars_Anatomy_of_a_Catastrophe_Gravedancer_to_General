import unittest

from src.utils.prompt_schema import TARGET_WORDS_PER_DAY
from src.utils.story_validator import deduplicate_story, strip_saved_episode_header, validate_story


class TestStoryValidator(unittest.TestCase):
    def test_deduplicate_story_removes_repeated_model_output(self):
        story = "## DAY 1: Ash\n\nA distinct paragraph with enough words to be considered content and not metadata.\n\nA distinct paragraph with enough words to be considered content and not metadata.\n\nA new paragraph with a different action, consequence, and sensory detail that moves the scene onward."
        cleaned, metrics = deduplicate_story(story)
        self.assertEqual(metrics["removed_paragraphs"], 1)
        self.assertNotIn("duplicated", cleaned)

    def test_deduplicate_story_removes_repeated_episode_header_lines(self):
        story = "\n\n".join([
            "# The Storm's Arithmetic",
            "**Generated:** 2026-07-19T19:26:42",
            "**Days:** 3",
            "**Target Jedi:** Unknown Jedi",
            "**Setting:** Ruined settlement",
        ] * 3)

        cleaned, metrics = deduplicate_story(story)

        self.assertEqual(metrics["removed_paragraphs"], 10)
        self.assertEqual(cleaned.count("# The Storm's Arithmetic"), 1)
        self.assertEqual(cleaned.count("**Generated:**"), 1)

    def test_strip_saved_episode_header_preserves_story_body(self):
        saved = "# Title\n\n**Days:** 3\n\n---\n\n## DAY 1: Ash\n\nThe story begins."
        self.assertEqual(strip_saved_episode_header(saved), "## DAY 1: Ash\n\nThe story begins.")
    def test_expected_day_count_and_total_word_budget_are_checked(self):
        story = "## DAY 1: Ashfall\n\n" + ("Ash and bone. " * 100)

        report = validate_story(story, expected_days=3)

        self.assertTrue(any("3 were requested" in warning for warning in report["warnings"]))
        expected_target = TARGET_WORDS_PER_DAY * 3
        self.assertTrue(any(f"target ~{expected_target:,}" in warning for warning in report["warnings"]))

    def test_empty_story_reports_missing_days_and_short_output(self):
        report = validate_story("", expected_days=3)

        self.assertIn("Story is empty.", report["warnings"])
        self.assertEqual(report["num_days_found"], 0)
