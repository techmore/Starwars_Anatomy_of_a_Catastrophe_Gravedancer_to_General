"""Tests for publishing safety and site-repository synchronization."""

import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from scripts import publish_episode


class TestPublishEpisode(unittest.TestCase):
    @staticmethod
    def _fixture(root: Path) -> tuple[Path, Path]:
        episode = root / "episode-test"
        site = root / "site"
        (episode / "images").mkdir(parents=True)
        (site / "episodes").mkdir(parents=True)
        (site / "build.py").write_text("# fixture\n", encoding="utf-8")
        (episode / "metadata.json").write_text(json.dumps({
            "title": "Dry Run Fixture",
            "jedi_name": "Test Jedi",
            "setting": "Test setting",
            "created_at": "2026-09-23T00:00:00",
            "pipeline_complete": True,
            "num_days": 1,
        }), encoding="utf-8")
        (episode / "story.md").write_text(
            "# Dry Run Fixture\n\n## DAY 1: Arrival\n\n"
            "A short fixture story for validation.\n",
            encoding="utf-8",
        )
        Image.new("RGB", (4, 4), "red").save(episode / "images" / "day-00-banner.png")
        Image.new("RGB", (4, 4), "blue").save(episode / "images" / "day-01-arrival-hero.png")
        return episode, site

    @staticmethod
    def _args(episode: Path, site: Path, *, dry_run: bool) -> Namespace:
        return Namespace(
            episode_dir=str(episode),
            site_repo=str(site),
            mark_complete=False,
            episode=None,
            status="draft",
            tagline=None,
            jedi_fate=None,
            dry_run=dry_run,
            no_push=True,
        )

    def test_dry_run_does_not_write_site_assets_or_pull(self):
        with tempfile.TemporaryDirectory() as raw:
            episode, site = self._fixture(Path(raw))

            with patch.object(publish_episode, "run_git") as run_git:
                publish_episode.action_publish(self._args(episode, site, dry_run=True))

            run_git.assert_not_called()
            self.assertEqual(
                sorted(path.relative_to(site) for path in site.rglob("*") if path.is_file()),
                [Path("build.py")],
            )

    def test_publish_pulls_before_numbering_and_removes_old_downloads(self):
        with tempfile.TemporaryDirectory() as raw:
            episode, site = self._fixture(Path(raw))
            download_dir = site / "assets" / "downloads" / "01-dry-run-fixture"
            download_dir.mkdir(parents=True)
            (download_dir / "2026-09-01-01-dry-run-fixture.pdf").write_bytes(b"old")
            (download_dir / "2026-09-01-01-dry-run-fixture.epub").write_bytes(b"old")

            calls = []

            def fake_git(repo, *args, **kwargs):
                calls.append((repo, args, kwargs))
                return ""

            with patch.object(publish_episode, "run_git", side_effect=fake_git):
                publish_episode.action_publish(self._args(episode, site, dry_run=False))

            self.assertEqual(calls[0][1], ("pull", "--ff-only"))
            self.assertFalse((download_dir / "2026-09-01-01-dry-run-fixture.pdf").exists())
            self.assertFalse((download_dir / "2026-09-01-01-dry-run-fixture.epub").exists())
            self.assertTrue((download_dir / "2026-09-23-01-dry-run-fixture.pdf").exists())
            self.assertTrue((site / "episodes" / "01-dry-run-fixture.md").exists())


if __name__ == "__main__":
    unittest.main()
