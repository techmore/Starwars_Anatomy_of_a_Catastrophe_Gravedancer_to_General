"""Tests for the OpenCode CLI harness integration."""

import subprocess
import unittest
from unittest.mock import patch

from src.utils import harness as harness_mod


class TestOpenCodeHarness(unittest.TestCase):
    def test_opencode_harness_registered_and_cross_platform(self):
        oc = harness_mod.by_id("opencode")
        self.assertEqual(oc.id, "opencode")
        self.assertEqual(oc.kind, "opencode_cli")
        self.assertTrue(oc.on_platform("darwin"))
        self.assertTrue(oc.on_platform("linux"))

    def test_pipeline_model_ref_maps_alias_to_target(self):
        oc = harness_mod.by_id("opencode")
        ref = harness_mod.pipeline_model_ref(oc, "ox-alpha-free")
        self.assertEqual(ref, "opencode:opencode/x-preview-f-free")

    def test_pipeline_model_ref_alias_env_override(self):
        oc = harness_mod.by_id("opencode")
        with patch.dict(os_environ(), {"GRAVEDANCER_OXALPHA_MODEL": "opencode/hy3-free"}):
            ref = harness_mod.pipeline_model_ref(oc, "ox-alpha-free")
        self.assertEqual(ref, "opencode:opencode/hy3-free")

    def test_pipeline_model_ref_passthrough(self):
        oc = harness_mod.by_id("opencode")
        ref = harness_mod.pipeline_model_ref(oc, "opencode/glm-5.3")
        self.assertEqual(ref, "opencode:opencode/glm-5.3")

    def test_list_opencode_models_parses_cli_output(self):
        fake = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout="opencode/glm-5.3\nopencode/hy3-free\nopencode/glm-5.3\nno-slash-line\n",
            stderr="",
        )
        with patch.object(harness_mod.subprocess, "run", return_value=fake):
            models = harness_mod.list_opencode_models()
        self.assertEqual(models, ["opencode/glm-5.3", "opencode/hy3-free"])

    def test_list_opencode_models_swallows_missing_binary(self):
        with patch.object(harness_mod.subprocess, "run", side_effect=OSError("nope")):
            self.assertEqual(harness_mod.list_opencode_models(), [])

    def test_model_choices_order_alias_free_rest(self):
        fake_models = [
            "opencode-go/qwen3.8-max",
            "opencode/hy3-free",
            "opencode/x-preview-f-free",
            "opencode/claude-opus-4-8",
        ]
        with patch.object(harness_mod, "list_opencode_models", return_value=fake_models):
            choices = harness_mod.list_opencode_model_choices()
        self.assertEqual(choices[0], "ox-alpha-free")
        self.assertEqual(choices[1:3], ["opencode/hy3-free", "opencode/x-preview-f-free"])
        self.assertIn("opencode-go/qwen3.8-max", choices)

    def test_health_check_reports_missing_binary(self):
        oc = harness_mod.by_id("opencode")
        with patch.object(harness_mod.shutil, "which", return_value=None):
            result = harness_mod.health_check(oc)
        self.assertFalse(result["ok"])
        self.assertIn("not found on PATH", str(result["error"]))

    def test_health_check_ok_with_models(self):
        oc = harness_mod.by_id("opencode")
        with patch.object(harness_mod.shutil, "which", return_value="/usr/local/bin/opencode"), \
             patch.object(harness_mod, "list_opencode_models", return_value=["opencode/hy3-free"]):
            result = harness_mod.health_check(oc)
        self.assertTrue(result["ok"])
        self.assertEqual(result["models"], ["opencode/hy3-free"])


def os_environ():
    import os

    return os.environ


if __name__ == "__main__":
    unittest.main()
