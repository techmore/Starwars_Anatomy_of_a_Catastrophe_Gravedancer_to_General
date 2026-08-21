import os
import unittest
from pathlib import Path
from unittest.mock import patch

from src.utils.models import DEFAULT_MODEL
from src.utils.settings import PROJECT_ROOT, load_settings, stage_model


class TestSettings(unittest.TestCase):
    def test_defaults_are_repository_deterministic(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = load_settings()

        self.assertEqual(settings.model, DEFAULT_MODEL)
        self.assertEqual(settings.storage_path, PROJECT_ROOT / "episodes")
        self.assertEqual(settings.log_path, PROJECT_ROOT / "log")

    def test_environment_overrides_are_expanded(self):
        with patch.dict(
            os.environ,
            {
                "GRAVEDANCER_MODEL": "lmstudio:ornith-1.5-9b",
                "GRAVEDANCER_STORAGE_PATH": "~/gravedancer-benchmark",
                "GRAVEDANCER_LOG_PATH": "~/gravedancer-logs",
            },
            clear=True,
        ):
            settings = load_settings()

        self.assertEqual(settings.model, "lmstudio:ornith-1.5-9b")
        self.assertEqual(settings.storage_path, Path("~/gravedancer-benchmark").expanduser())
        self.assertEqual(settings.log_path, Path("~/gravedancer-logs").expanduser())

    def test_blank_model_falls_back_to_default(self):
        with patch.dict(os.environ, {"GRAVEDANCER_MODEL": "   "}, clear=True):
            settings = load_settings()

        self.assertEqual(settings.model, DEFAULT_MODEL)


class TestStageModelRouting(unittest.TestCase):
    def test_main_model_used_without_overrides(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(stage_model("outline", "main-model"), "main-model")
            self.assertEqual(stage_model("recap", "main-model"), "main-model")

    def test_env_override_applies_per_stage_only(self):
        env = {
            "GRAVEDANCER_MODEL_OUTLINE": "planner",
            "GRAVEDANCER_MODEL_STORY": "writer",
        }
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(stage_model("outline", "main"), "planner")
            self.assertEqual(stage_model("story", "main"), "writer")
            self.assertEqual(stage_model("recap", "main"), "main")
            self.assertEqual(stage_model("visual", "main"), "main")

    def test_cli_override_wins_over_env(self):
        with patch.dict(os.environ, {"GRAVEDANCER_MODEL_STORY": "env-writer"}, clear=True):
            self.assertEqual(stage_model("story", "main", "flag-writer"), "flag-writer")

    def test_blank_values_fall_through_to_main(self):
        with patch.dict(os.environ, {"GRAVEDANCER_MODEL_VISUAL": "  "}, clear=True):
            self.assertEqual(stage_model("visual", "main", ""), "main")
            self.assertEqual(stage_model("unknown-stage", "main", "  "), "main")
