import json
import tempfile
import unittest
from pathlib import Path

from scripts.run_model_trials import (
    DEFAULT_MODEL_REPOS,
    _episode_summary,
    _pipeline_env,
    model_target_dir,
    pipeline_command,
    slugify,
    smoke_command,
)


class TestRunModelTrials(unittest.TestCase):
    def test_default_models_are_the_two_bakeoff_targets(self):
        self.assertEqual(DEFAULT_MODEL_REPOS, (
            "mlx-community/gemma-4-26B-A4B-it-OptiQ-4bit",
            "mlx-community/Qwen3.8-27B-OptiQ-4bit",
        ))

    def test_slugify_and_model_target_dir_are_stable(self):
        self.assertEqual(slugify("mlx-community/Qwen3.8-27B-OptiQ-4bit"), "mlx-community-Qwen3.8-27B-OptiQ-4bit")
        self.assertEqual(
            model_target_dir(Path("/models"), "org/model"),
            Path("/models/org-model"),
        )

    def test_pipeline_command_uses_the_project_entrypoint(self):
        command = pipeline_command(Path("/models/qwen"), seed=2)
        self.assertEqual(command[1], str(Path(__file__).parents[1] / "run_creative_pipeline.py"))
        self.assertIn("/models/qwen", command)
        self.assertIn("2", command)

    def test_smoke_command_writes_a_machine_readable_report(self):
        command = smoke_command(Path("/models/qwen"), max_tokens=512, report_path=Path("/tmp/smoke.json"))
        self.assertIn("benchmark_model.py", command[1])
        self.assertIn("512", command)
        self.assertIn("/tmp/smoke.json", command)

    def test_trial_environment_forces_one_model_and_offline_mode(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env = _pipeline_env(
                trial_storage=Path(temp_dir),
                model_path=Path("/models/qwen"),
                daily_target_tokens=8000,
            )
        self.assertEqual(env["GRAVEDANCER_MODEL"], "/models/qwen")
        self.assertEqual(env["GRAVEDANCER_DAILY_TARGET_TOKENS"], "8000")
        self.assertEqual(env["GRAVEDANCER_ALLOW_MODEL_DOWNLOADS"], "0")
        self.assertNotIn("GRAVEDANCER_MODEL_STORY", env)

    def test_episode_summary_reports_completed_story_and_checkpoint(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            episode = root / "episodes" / "episode-1"
            episode.mkdir(parents=True)
            (episode / "metadata.json").write_text(json.dumps({
                "title": "Trial",
                "pipeline_complete": True,
                "word_count": 123,
            }), encoding="utf-8")
            (episode / "story.md").write_text("story", encoding="utf-8")
            checkpoints = root / "episodes" / ".checkpoints"
            checkpoints.mkdir()
            (checkpoints / "one.json").write_text("{}", encoding="utf-8")

            summary = _episode_summary(root)

        self.assertEqual(summary["episode_count"], 1)
        self.assertEqual(summary["completed_count"], 1)
        self.assertEqual(summary["checkpoint_count"], 1)
        self.assertEqual(summary["episodes"][0]["word_count"], 123)


if __name__ == "__main__":
    unittest.main()
