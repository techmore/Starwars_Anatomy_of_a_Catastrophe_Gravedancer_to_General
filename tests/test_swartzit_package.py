import json
import tempfile
import unittest
from pathlib import Path

from src.utils.swartzit_package import CONTENT_PACKAGE_FORMAT, episode_to_package, split_story_days


class TestSwartzitPackage(unittest.TestCase):
    def test_split_story_days_preserves_order_and_body(self):
        days = split_story_days(
            "# Episode\n\n---\n\n## DAY 1: Ashfall\n\nThe rain begins.\n\n"
            "## DAY 2: Bone Wind\n\nThe hunt continues."
        )
        self.assertEqual([day["id"] for day in days], ["day-1", "day-2"])
        self.assertEqual(days[0]["title"], "Ashfall")
        self.assertEqual(days[1]["body"], "The hunt continues.")

    def test_existing_episode_becomes_a_versioned_package(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "episode-001"
            (root / "images").mkdir(parents=True)
            (root / "metadata.json").write_text(
                json.dumps({
                    "id": "episode-001",
                    "title": "Ash and Bone",
                    "num_days": 2,
                    "setting": "Kalee",
                    "seed_value": 42,
                    "model_story": "gemma",
                    "pipeline_complete": True,
                }),
                encoding="utf-8",
            )
            (root / "story.md").write_text(
                "# Ash and Bone\n\n---\n\n## DAY 1: Ashfall\n\nOne.\n\n## DAY 2: Bone Wind\n\nTwo.",
                encoding="utf-8",
            )
            (root / "images" / "cover.png").write_bytes(b"png")

            package = episode_to_package(root)

            self.assertEqual(package["format"], CONTENT_PACKAGE_FORMAT)
            self.assertEqual(package["pack"]["id"], "starwars.gravedancer")
            self.assertEqual([unit["order"] for unit in package["units"]], [1, 2])
            self.assertEqual(package["assets"][0]["relative_path"], "images/cover.png")
            self.assertEqual(package["feed_item"]["media"][0]["path"], str(root.resolve() / "images/cover.png"))
            self.assertTrue(package["provenance"]["pipeline_complete"])


if __name__ == "__main__":
    unittest.main()
