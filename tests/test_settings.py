import os
import unittest
from pathlib import Path
from unittest.mock import patch

from src.utils.models import DEFAULT_MODEL
from src.utils.settings import PROJECT_ROOT, load_settings


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
