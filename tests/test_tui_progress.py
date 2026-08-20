"""Tests for the TUI RunProgress parser."""

import unittest

from tui import RunProgress, _progress_bar


LINES = [
    "CREATIVE SEED (value=42)",
    "  Days:   6",
    "  PHASE 1: OUTLINE — \"The Ashen Chain\"",
    "  [outline] Building episode outline... | ~1,200 tokens | ~8.0 tok/s",
    "Outline generated (5,210 chars) in 640.0s",
    "  PHASE 2: STORY GENERATION",
    "  [section] Day 1: expanding section 1/5",
    "  [section] Day 1: expanding section 3/5",
    "  [day] Day 1 complete (4,008 chars).",
    "  [section] Day 4: expanding section 2/5",
    "  [day] Day 6 complete (4,223 chars).",
    "Story generated (23,762 chars, 3,993 words) in 3600.0s",
    "  Extracted 30 chapters across 6 days",
    "  PHASE 4: BANNER PROMPT",
    "  Banner prompt generated in 12.0s",
    "  Chapter 12/30 (Day 3, Ch 2: The Echo Plays)... done (9.0s)",
    "  Chapter 30/30 (Day 6, Ch 5: The General's First Mask)... done (8.0s)",
    "  Episode saved: episodes/episode-20260820-x/",
]


class TestRunProgress(unittest.TestCase):
    def setUp(self):
        self.p = RunProgress()
        for line in LINES:
            self.p.update(line)

    def test_days_captured(self):
        self.assertEqual(self.p.num_days, 6)

    def test_reaches_100_on_save(self):
        self.assertEqual(self.p.pct, 100.0)
        self.assertEqual(self.p.stage, "saved")

    def test_story_anchor_after_outline(self):
        p = RunProgress()
        for line in LINES[:5]:
            p.update(line)
        self.assertGreaterEqual(p.pct, 10.0)

    def test_story_fraction_tracks_day_and_section(self):
        p = RunProgress()
        for line in LINES[:7]:  # through Day 1 section 1/5
            p.update(line)
        expected = 10 + 70 * ((1 - 1) + 0 / 5) / 6
        self.assertAlmostEqual(p.pct, expected, places=1)

    def test_chapter_prompt_progress(self):
        p = RunProgress()
        for line in LINES[:-1]:  # through Chapter 30/30, before save
            p.update(line)
        # last chapter prompt line: 83 + 15*(30/30) = 98
        self.assertAlmostEqual(p.pct, 98.0, places=1)
        self.assertEqual(p.stage, "chapter prompts 30/30")
        self.assertEqual(p.chapters_total, 30)

    def test_pct_monotonic(self):
        p = RunProgress()
        last = 0.0
        for line in LINES:
            p.update(line)
            self.assertGreaterEqual(p.pct, last - 1e-9)
            last = p.pct

    def test_label_suffix_contains_bar_and_stage(self):
        suffix = self.p.label_suffix()
        self.assertIn("100%", suffix)
        self.assertIn("█" * 10, suffix)
        self.assertIn("saved", suffix)

    def test_bar_rendering(self):
        self.assertEqual(_progress_bar(0), "░" * 10)
        self.assertEqual(_progress_bar(100), "█" * 10)
        self.assertEqual(_progress_bar(50), "█" * 5 + "░" * 5)


class TestRunProgressTree(unittest.TestCase):
    def feed(self, lines):
        p = RunProgress()
        for line in lines:
            p.update(line)
        return p

    def test_sections_and_tokens_tracked(self):
        p = RunProgress()
        for line in [
            "  Days:   6",
            "Outline generated (5,210 chars) in 640.0s",
            "  [outline] Building episode outline... | ~4,800 tokens | ~7.5 tok/s",
            "  PHASE 2: STORY GENERATION",
            "  [section] Day 1: expanding section 1/5",
            "  [day-1-section-1] Streaming Day 1 section 1... | ~3,900 tokens | ~8.1 tok/s",
            "  [section] Day 1: expanding section 2/5",
            "  [day-1-section-2] Streaming Day 1 section 2... | ~4,100 tokens | ~8.0 tok/s",
            "  [day] Day 1 complete (4,008 chars).",
        ]:
            p.update(line)
        self.assertEqual(p.outline_tokens, 4800)
        d1 = p.days[1]
        self.assertTrue(d1["done"])
        self.assertEqual(d1["tokens"][1], 3900)
        self.assertEqual(d1["tokens"][2], 4100)
        self.assertEqual(p.tokens_total, 4800 + 3900 + 4100)

    def test_checkpoint_reuse_marks_day_done(self):
        p = RunProgress()
        for line in ["  Days:   6", "[checkpoint] Reusing checkpoint for Day 2."]:
            p.update(line)
        self.assertTrue(p.days[2]["done"])

    def test_tree_renders_runtime_and_chips(self):
        p = self.feed(LINES[:13])  # through "Extracted 30 chapters"
        tree = p.render_tree(3725)
        self.assertIn("runtime 1:02:05", tree)
        self.assertIn("outline", tree)
        self.assertIn("D1", tree)
        self.assertIn("visual prompts", tree)

    def test_tree_shows_active_chapter(self):
        p = RunProgress()
        for line in ["  Days:   6", "  PHASE 2: STORY GENERATION",
                     "  [section] Day 3: expanding section 2/5",
                     "  [day-3-section-2] ... | ~1,900 tokens | ~8.0 tok/s"]:
            p.update(line)
        tree = p.render_tree(65)
        self.assertIn("ch2/5", tree)
        self.assertIn("1.9k", tree)
        self.assertIn("D3", tree)
        self.assertIn("▶", tree)

    def test_visual_prompt_counter_in_tree(self):
        p = self.feed(LINES)  # full sequence incl. save
        tree = p.render_tree(4000)
        self.assertIn("30/30", tree)


if __name__ == "__main__":
    unittest.main()
