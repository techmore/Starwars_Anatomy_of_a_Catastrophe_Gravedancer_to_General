"""Tests for the cross-platform Ollama harness mapping."""

import unittest

from src.utils import harness as harness_mod


class TestOllamaHarness(unittest.TestCase):
    def test_ollama_harness_is_available_on_linux(self):
        ollama = harness_mod.by_id("ollama")
        self.assertTrue(ollama.on_platform("linux"))
        self.assertEqual(ollama.kind, "openai_http")

    def test_pipeline_model_ref_uses_ollama_prefix(self):
        ollama = harness_mod.by_id("ollama")
        self.assertEqual(
            harness_mod.pipeline_model_ref(ollama, "gemma4:e4b"),
            "ollama:gemma4:e4b",
        )

    def test_pipeline_environment_uses_ollama_endpoint(self):
        ollama = harness_mod.by_id("ollama")
        self.assertEqual(
            harness_mod.pipeline_environment(ollama, "http://127.0.0.1:11434"),
            {"GRAVEDANCER_OLLAMA_URL": "http://127.0.0.1:11434/v1/chat/completions"},
        )


if __name__ == "__main__":
    unittest.main()
