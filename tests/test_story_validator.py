import unittest

from src.utils.prompt_schema import TARGET_WORDS_PER_DAY
from src.utils.story_validator import (
    deduplicate_story,
    near_duplicate_paragraphs,
    strip_saved_episode_header,
    validate_story,
)


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


class CanonCheckTests(unittest.TestCase):
    """Era guard: the series is explicitly pre-Clone Wars."""

    def test_flags_clone_troopers_and_separatists(self):
        story = ("## DAY 1: Ash\n\nA squad of clone troopers held the line "
                 "while the Separatist fleet burned above.")
        report = validate_story(story)
        canon = [w for w in report["warnings"] if w.startswith("canon:")]
        self.assertEqual(len(canon), 2)
        self.assertTrue(any("clone troopers" in w for w in canon))

    def test_flags_qymaen_wielding_a_lightsaber(self):
        story = "## DAY 1: Ash\n\nQymaen ignited his lightsaber and strode into the fray."
        report = validate_story(story)
        self.assertTrue(any("lightsaber" in w for w in report["warnings"]))

    def test_allows_jedi_lightsabers_and_clean_prose(self):
        story = ("## DAY 1: Ash\n\nThe Jedi ignited her lightsaber. "
                 "Qymaen worked the rifle's bolt and answered with lead.")
        report = validate_story(story, expected_days=1)
        self.assertFalse([w for w in report["warnings"] if w.startswith("canon:")])


class NearDuplicateParagraphTests(unittest.TestCase):
    """Paraphrase-loop detection (the Forgotten Chain ending failure mode)."""

    BASE = ("In the silence of space, Qymaen found himself reflecting on the "
            "nature of his own existence and the choices he had made along "
            "the long path of war that had brought him to this distant and "
            "quiet place above the world of his birth.")

    def test_exact_repeat_flagged_by_validate(self):
        story = f"## DAY 1: Ash\n\n{self.BASE}\n\n{self.BASE}"
        report = validate_story(story, expected_days=1)
        # Exact repeats are caught by the existing paragraph check…
        self.assertTrue(any("duplicated paragraph" in w for w in report["warnings"]))

    def test_paraphrased_repeat_caught_by_shingle_overlap(self):
        # A real generation loop drifts by a word or two, not a full rewrite.
        variant = ("In the silence of space, Qymaen found himself reflecting "
                   "on the nature of his own existence and the choices he had "
                   "made along the long path of war that had carried him to "
                   "this distant and quiet place above the world of his birth.")
        flagged = near_duplicate_paragraphs(f"{self.BASE}\n\n{variant}")
        self.assertEqual(len(flagged), 1)

    def test_distinct_paragraphs_not_flagged(self):
        other = ("The market at dawn smelled of wet stone and frying grain. "
                 "Vendors called prices across the square while children "
                 "chased a wheel rim down the gutter between the stalls.")
        self.assertEqual(near_duplicate_paragraphs(f"{self.BASE}\n\n{other}"), [])
