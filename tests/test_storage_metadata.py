import json
import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from src.utils.storage import EpisodeStorage


class TestEpisodeStorageMetadata(unittest.TestCase):
    def test_checkpoint_is_atomic_and_separate_from_episode_library(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = EpisodeStorage(tmpdir)
            checkpoint = storage.save_checkpoint(
                "Checkpoint Title",
                {"num_days": 2, "jedi_name": "Jedi"},
                {1: "## DAY 1: Ashfall\n\nDraft"},
                outline="## DAY 1: Ashfall",
                day_recaps={1: "Qymaen lost an eye; the Jedi fled north."},
            )

            self.assertTrue(checkpoint.exists())
            payload = json.loads(checkpoint.read_text(encoding="utf-8"))
            self.assertEqual(payload["title"], "Checkpoint Title")
            self.assertEqual(payload["day_drafts"]["1"], "## DAY 1: Ashfall\n\nDraft")
            self.assertEqual(payload["day_recaps"]["1"], "Qymaen lost an eye; the Jedi fled north.")
            self.assertEqual(storage.list_episodes(), [])

            checkpoints = storage.list_checkpoints()
            self.assertEqual(len(checkpoints), 1)
            loaded = storage.load_checkpoint(checkpoints[0]["path"])
            self.assertEqual(loaded["title"], "Checkpoint Title")
            self.assertIsNone(storage.load_checkpoint(str(Path(tmpdir) / "outside.json")))
            self.assertTrue(storage.delete_checkpoint("Checkpoint Title"))
            self.assertEqual(storage.list_checkpoints(), [])
            self.assertFalse(storage.delete_checkpoint("Checkpoint Title"))

    def test_same_title_saves_distinct_episode_ids(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = EpisodeStorage(tmpdir)
            metadata = {"num_days": 1, "jedi_name": "Jedi", "setting": "Kalee"}

            first = storage.save_episode("Same Title", "first", metadata)
            second = storage.save_episode("Same Title", "second", metadata)

            self.assertNotEqual(first, second)
            self.assertEqual(storage.load_episode(first)["story"].split("---\n\n", 1)[1], "first")
            self.assertEqual(storage.load_episode(second)["story"].split("---\n\n", 1)[1], "second")

    def test_update_episode_can_save_empty_story(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = EpisodeStorage(tmpdir)
            episode_id = storage.save_episode(
                "Editable", "original", {"num_days": 1, "jedi_name": "Jedi", "setting": "Kalee"}
            )

            self.assertTrue(storage.update_episode(episode_id, story=""))
            loaded = storage.load_episode(episode_id)
            self.assertEqual(loaded["story"].split("---\n\n", 1)[1], "")

    def test_invalid_ids_and_filenames_cannot_escape_storage_root(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = EpisodeStorage(tmpdir)
            episode_id = storage.save_episode(
                "Safe", "story", {"num_days": 1, "jedi_name": "Jedi", "setting": "Kalee"}
            )

            self.assertIsNone(storage.load_episode("../outside"))
            self.assertFalse(storage.delete_episode("../outside"))
            with self.assertRaises(ValueError):
                storage.write_episode_bundle(episode_id, "../outside.json")

            rel = storage.save_image(episode_id, 1, "../../outside/frame", b"png")
            self.assertTrue(rel.startswith(f"{episode_id}/images/"))
            self.assertFalse((Path(tmpdir).parent / "outside").exists())

    def test_malformed_metadata_does_not_break_library_listing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = EpisodeStorage(tmpdir)
            broken = Path(tmpdir) / "episode-broken"
            broken.mkdir()
            (broken / "metadata.json").write_text("{not json", encoding="utf-8")

            self.assertEqual(storage.list_episodes(), [])
            self.assertIsNone(storage.load_episode("episode-broken"))

    def test_target_jedi_name_fallback_and_header(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = EpisodeStorage(tmpdir)
            metadata = {
                "title": "Ash and Bone",
                "num_days": 5,
                "target_jedi_name": "Vex'arii",
                "jedi_name": "Should Not Win",
                "setting": "Kalee",
            }

            episode_id = storage.save_episode(
                title=metadata["title"],
                story="## DAY 1: Ashfall\n\nThe hunt begins.",
                metadata=metadata,
            )

            loaded = storage.load_episode(episode_id)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["metadata"]["target_jedi_name"], "Vex'arii")

            story_path = Path(tmpdir) / episode_id / "story.md"
            story_text = story_path.read_text()
            self.assertIn("**Target Jedi:** Vex'arii", story_text)
            self.assertNotIn("**Jedi Target:**", story_text)

    def test_storage_methods_emit_useful_logs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = EpisodeStorage(tmpdir)
            with self.assertLogs("src.utils.storage", level="INFO") as logs:
                episode_id = storage.save_episode(
                    title="Log Test",
                    story="## DAY 1: Dawn\n\nThe hunt begins.",
                    metadata={
                        "title": "Log Test",
                        "num_days": 2,
                        "jedi_name": "Log Jedi",
                        "setting": "Kalee",
                    },
                )
                loaded = storage.load_episode(episode_id)
                bundle = storage.export_episode_bundle(episode_id)
                archive_bytes = storage.build_episode_archive_bytes(episode_id)
                storage.list_episodes()

            self.assertIsNotNone(loaded)
            self.assertIsNotNone(bundle)
            self.assertIsNotNone(archive_bytes)
            joined = "\n".join(logs.output)
            self.assertIn("save_episode start", joined)
            self.assertIn("save_episode end", joined)
            self.assertIn("load_episode start", joined)
            self.assertIn("load_episode end", joined)
            self.assertIn("export_episode_bundle start", joined)
            self.assertIn("export_episode_bundle end", joined)
            self.assertIn("build_episode_archive_bytes start", joined)
            self.assertIn("build_episode_archive_bytes end", joined)
            self.assertIn("list_episodes start", joined)
            self.assertIn("list_episodes end", joined)

    def test_old_field_still_works_for_compatibility(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = EpisodeStorage(tmpdir)
            episode_id = storage.save_episode(
                title="Bone Wind",
                story="## DAY 1: Arrival\n\nA storm gathers.",
                metadata={
                    "title": "Bone Wind",
                    "num_days": 3,
                    "jedi_name": "Legacy Jedi",
                    "setting": "Jabiim",
                },
            )

            episodes = storage.list_episodes()
            self.assertEqual(episodes[0]["target_jedi_name"], "Legacy Jedi")
            self.assertEqual(episodes[0]["jedi_name"], "Legacy Jedi")

            loaded = storage.load_episode(episode_id)
            self.assertEqual(loaded["metadata"]["jedi_name"], "Legacy Jedi")

    def test_list_episodes_defaults_prompt_counts_to_zero_without_prompts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = EpisodeStorage(tmpdir)
            storage.save_episode(
                title="No Prompts",
                story="## DAY 1: Arrival\n\nA storm gathers.",
                metadata={
                    "title": "No Prompts",
                    "num_days": 2,
                    "jedi_name": "Silent Jedi",
                    "setting": "Bespin",
                },
            )

            episodes = storage.list_episodes()

            self.assertEqual(episodes[0]["prompt_sets"], 0)
            self.assertEqual(episodes[0]["prompt_days"], 0)

    def test_list_episodes_includes_prompt_coverage_counts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = EpisodeStorage(tmpdir)
            storage.save_episode(
                title="Coverage Test",
                story="## DAY 1: Dawn\n\nThe hunt begins.",
                metadata={
                    "title": "Coverage Test",
                    "num_days": 3,
                    "jedi_name": "Coverage Jedi",
                    "setting": "Mustafar",
                },
                prompts={
                    "scenes": [
                        {"day": 1, "prompt_type": "Flux.2 Klein 4b - DrawThings"},
                        {"day": 1, "prompt_type": "Flux.2 Klein 4b - DrawThings"},
                        {"day": 3, "prompt_type": "Flux.2 Klein 4b - DrawThings"},
                    ],
                    "aspect_ratio": "16:9",
                },
            )

            episodes = storage.list_episodes()

            self.assertEqual(episodes[0]["prompt_sets"], 3)
            self.assertEqual(episodes[0]["prompt_days"], 2)

    def test_export_bundle_and_list_episodes_share_prompt_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = EpisodeStorage(tmpdir)
            episode_id = storage.save_episode(
                title="Shared Summary",
                story="## DAY 1: Dawn\n\nThe hunt begins.",
                metadata={
                    "title": "Shared Summary",
                    "num_days": 4,
                    "jedi_name": "Shared Jedi",
                    "setting": "Naboo",
                },
                prompts={
                    "scenes": [
                        {"day": 1, "prompt_type": "Flux.2 Klein 4b - DrawThings"},
                        {"day": 2, "prompt_type": "Flux.2 Klein 4b - DrawThings"},
                        {"day": 2, "prompt_type": "Flux.2 Klein 4b - DrawThings"},
                        {"day": 4, "prompt_type": "Flux.2 Klein 4b - DrawThings"},
                    ],
                    "aspect_ratio": "16:9",
                },
            )

            bundle = storage.export_episode_bundle(episode_id)
            episodes = storage.list_episodes()

            self.assertEqual(bundle["prompt_sets"], 4)
            self.assertEqual(bundle["prompt_days"], 3)
            self.assertEqual(episodes[0]["prompt_sets"], 4)
            self.assertEqual(episodes[0]["prompt_days"], 3)

    def test_load_episode_normalizes_legacy_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = EpisodeStorage(tmpdir)
            episode_id = storage.save_episode(
                title="Legacy Load",
                story="## DAY 1: Arrival\n\nA storm gathers.",
                metadata={
                    "title": "Legacy Load",
                    "num_days": 3,
                    "jedi_name": "Load Jedi",
                    "setting": "Jabiim",
                },
            )

            metadata_path = Path(tmpdir) / episode_id / "metadata.json"
            raw = json.loads(metadata_path.read_text())
            self.assertEqual(raw["jedi_name"], "Load Jedi")

            loaded = storage.load_episode(episode_id)
            self.assertEqual(loaded["metadata"]["jedi_name"], "Load Jedi")
            self.assertEqual(loaded["metadata"]["target_jedi_name"], "Load Jedi")

    def test_update_episode_preserves_and_normalizes_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = EpisodeStorage(tmpdir)
            episode_id = storage.save_episode(
                title="Storm and Ash",
                story="## DAY 1: Arrival\n\nA hunt begins.",
                metadata={
                    "title": "Storm and Ash",
                    "num_days": 4,
                    "jedi_name": "Legacy Jedi",
                    "setting": "Jabiim",
                },
            )

            updated = storage.update_episode(
                episode_id=episode_id,
                story="## DAY 1: Arrival\n\nThe storm deepens.",
                metadata={
                    "jedi_name": "New Canonical Name",
                    "setting": "Kalee",
                },
            )
            self.assertTrue(updated)

            loaded = storage.load_episode(episode_id)
            self.assertEqual(loaded["metadata"]["jedi_name"], "New Canonical Name")
            self.assertEqual(loaded["metadata"]["target_jedi_name"], "New Canonical Name")
            self.assertEqual(loaded["metadata"]["setting"], "Kalee")

            story_text = (Path(tmpdir) / episode_id / "story.md").read_text()
            self.assertIn("**Target Jedi:** New Canonical Name", story_text)

    def test_prompts_round_trip_through_storage(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = EpisodeStorage(tmpdir)
            prompts = {
                "scenes": [
                    {
                        "day": 1,
                        "prompt_type": "Flux.2 Klein 4b - DrawThings",
                        "wide": "Wide prompt text",
                        "medium": "Medium prompt text",
                        "negative_prompt": "negative text",
                    }
                ],
                "aspect_ratio": "16:9",
            }

            episode_id = storage.save_episode(
                title="Prompt Bundle",
                story="## DAY 1: Dawn\n\nA scene unfolds.",
                metadata={
                    "title": "Prompt Bundle",
                    "num_days": 2,
                    "jedi_name": "Prompt Jedi",
                    "setting": "Ryloth",
                },
                prompts=prompts,
            )

            loaded = storage.load_episode(episode_id)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["prompts"], prompts)

            prompts_path = Path(tmpdir) / episode_id / "prompts.json"
            self.assertTrue(prompts_path.exists())
            self.assertEqual(json.loads(prompts_path.read_text()), prompts)

    def test_export_episode_bundle_is_canonical(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = EpisodeStorage(tmpdir)
            episode_id = storage.save_episode(
                title="Bundle Test",
                story="## DAY 1: Dawn\n\nThe hunt begins.",
                metadata={
                    "title": "Bundle Test",
                    "num_days": 2,
                    "target_jedi_name": "Bundle Jedi",
                    "setting": "Korriban",
                },
                prompts={
                    "scenes": [{"day": 1, "prompt_type": "Flux.2 Klein 4b - DrawThings"}],
                    "aspect_ratio": "21:9",
                },
            )

            bundle = storage.export_episode_bundle(episode_id)
            self.assertIsNotNone(bundle)
            self.assertEqual(bundle["episode_id"], episode_id)
            self.assertEqual(bundle["title"], "Bundle Test")
            self.assertEqual(bundle["setting"], "Korriban")
            self.assertEqual(bundle["num_days"], 2)
            self.assertEqual(bundle["metadata"]["target_jedi_name"], "Bundle Jedi")
            self.assertEqual(bundle["metadata"]["jedi_name"], "Bundle Jedi")
            self.assertEqual(bundle["prompts"]["aspect_ratio"], "21:9")
            self.assertEqual(bundle["prompt_sets"], 1)
            self.assertEqual(bundle["prompt_days"], 1)
            self.assertIn("metadata_json", bundle["files"])
            self.assertTrue(bundle["files"]["story_md"].endswith("story.md"))
            self.assertEqual(
                Path(bundle["files"]["metadata_json"]),
                Path(tmpdir) / episode_id / "metadata.json",
            )
            self.assertEqual(
                Path(bundle["files"]["prompts_json"]),
                Path(tmpdir) / episode_id / "prompts.json",
            )
            self.assertIn("manifest", bundle)
            self.assertEqual(bundle["manifest"]["episode_id"], episode_id)
            self.assertIn("metadata_json", bundle["manifest"]["files"])
            self.assertTrue(bundle["manifest"]["files"]["metadata_json"]["exists"])
            self.assertIn("sha256", bundle["manifest"]["files"]["story_md"])
            self.assertGreater(bundle["manifest"]["files"]["story_md"]["size_bytes"], 0)

    def test_write_episode_bundle_creates_matching_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = EpisodeStorage(tmpdir)
            episode_id = storage.save_episode(
                title="Bundle File",
                story="## DAY 1: Dawn\n\nThe hunt begins.",
                metadata={
                    "title": "Bundle File",
                    "num_days": 1,
                    "jedi_name": "Bundle File Jedi",
                    "setting": "Naboo",
                },
                prompts={
                    "scenes": [],
                    "aspect_ratio": "16:9",
                },
            )

            bundle_path = storage.write_episode_bundle(episode_id)
            self.assertIsNotNone(bundle_path)

            bundle_file = Path(bundle_path)
            self.assertTrue(bundle_file.exists())

            written = json.loads(bundle_file.read_text())
            bundle = storage.export_episode_bundle(episode_id)
            self.assertEqual(written, bundle)
            self.assertEqual(written["episode_id"], episode_id)
            self.assertEqual(written["title"], "Bundle File")
            self.assertEqual(written["setting"], "Naboo")
            self.assertIn("manifest", written)
            self.assertIn("bundle_json_sha256", written["manifest"])

    def test_write_episode_archive_includes_episode_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = EpisodeStorage(tmpdir)
            episode_id = storage.save_episode(
                title="Archive Test",
                story="## DAY 1: Dawn\n\nThe hunt begins.",
                metadata={
                    "title": "Archive Test",
                    "num_days": 2,
                    "target_jedi_name": "Archive Jedi",
                    "setting": "Mustafar",
                },
                prompts={
                    "scenes": [{"day": 1, "prompt_type": "Flux.2 Klein 4b - DrawThings"}],
                    "aspect_ratio": "4:3",
                },
            )

            archive_path = storage.write_episode_archive(episode_id)
            self.assertIsNotNone(archive_path)

            archive_file = Path(archive_path)
            self.assertTrue(archive_file.exists())

            with zipfile.ZipFile(archive_file, "r") as zf:
                names = set(zf.namelist())
                self.assertIn("bundle.json", names)
                self.assertIn("manifest.json", names)
                self.assertIn("metadata.json", names)
                self.assertIn("story.md", names)
                self.assertIn("prompts.json", names)

                bundle = json.loads(zf.read("bundle.json").decode("utf-8"))
                manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
                self.assertEqual(bundle["episode_id"], episode_id)
                self.assertEqual(bundle["title"], "Archive Test")
                self.assertEqual(bundle["setting"], "Mustafar")
                self.assertEqual(manifest["episode_id"], episode_id)
                self.assertEqual(manifest["files"]["story_md"]["filename"], "story.md")

            archive_bytes = storage.build_episode_archive_bytes(episode_id)
            self.assertIsNotNone(archive_bytes)
            with zipfile.ZipFile(io.BytesIO(archive_bytes), "r") as zf:
                self.assertIn("bundle.json", zf.namelist())
                self.assertIn("manifest.json", zf.namelist())
                bytes_bundle = json.loads(zf.read("bundle.json").decode("utf-8"))
                bytes_manifest = json.loads(zf.read("manifest.json").decode("utf-8"))

            with zipfile.ZipFile(archive_file, "r") as zf:
                file_bundle = json.loads(zf.read("bundle.json").decode("utf-8"))
                file_manifest = json.loads(zf.read("manifest.json").decode("utf-8"))

            self.assertEqual(bytes_bundle, file_bundle)
            self.assertEqual(bytes_manifest, file_manifest)
            self.assertEqual(bytes_manifest["files"]["story_md"]["sha256"], file_manifest["files"]["story_md"]["sha256"])

    def test_write_episode_archive_includes_saved_media(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = EpisodeStorage(tmpdir)
            episode_id = storage.save_episode(
                "Archive Media",
                "## DAY 1: Dawn\n\nThe hunt begins.",
                {"num_days": 1, "jedi_name": "Archive Jedi", "setting": "Kalee"},
            )
            storage.save_image(episode_id, day=1, shot="keyframe", image_bytes=b"png")

            archive_bytes = storage.build_episode_archive_bytes(episode_id)

            with zipfile.ZipFile(io.BytesIO(archive_bytes), "r") as zf:
                self.assertIn("images/day-01-keyframe.png", zf.namelist())
                self.assertEqual(zf.read("images/day-01-keyframe.png"), b"png")

    def test_write_episode_archive_omits_prompts_when_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = EpisodeStorage(tmpdir)
            episode_id = storage.save_episode(
                title="Archive No Prompts",
                story="## DAY 1: Dawn\n\nThe hunt begins.",
                metadata={
                    "title": "Archive No Prompts",
                    "num_days": 1,
                    "jedi_name": "Archive Jedi",
                    "setting": "Dagobah",
                },
            )

            archive_bytes = storage.build_episode_archive_bytes(episode_id)
            self.assertIsNotNone(archive_bytes)

            with zipfile.ZipFile(io.BytesIO(archive_bytes), "r") as zf:
                names = set(zf.namelist())
                self.assertIn("bundle.json", names)
                self.assertIn("manifest.json", names)
                self.assertIn("metadata.json", names)
                self.assertIn("story.md", names)
                self.assertNotIn("prompts.json", names)
                manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
                self.assertFalse(manifest["files"]["prompts_json"]["exists"])
