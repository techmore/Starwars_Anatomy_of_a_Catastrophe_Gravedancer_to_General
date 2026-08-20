import os
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.utils.mlx_client import BONSAI_1BIT_MODEL, MLXClient, _apply_chat_template, _configure_local_model_mode, _redact_command_arguments


class TestChatTemplate(unittest.TestCase):
    def test_lmstudio_health_reports_unavailable_server(self):
        client = MLXClient("lmstudio:ornith-1.5-9b")
        with patch("src.utils.mlx_client.urllib.request.urlopen", side_effect=ConnectionRefusedError(61, "refused")):
            status = client.check_lmstudio()
        self.assertFalse(status["available"])
        self.assertFalse(status["model_loaded"])

    def test_lmstudio_health_reports_loaded_model(self):
        client = MLXClient("lmstudio:ornith-1.5-9b")

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def read(self):
                return b'{"data":[{"id":"ornith-1.5-9b"}]}'

        with patch("src.utils.mlx_client.urllib.request.urlopen", return_value=Response()):
            status = client.check_lmstudio()
        self.assertTrue(status["available"])
        self.assertTrue(status["model_loaded"])

    def test_lmstudio_generation_fails_fast_when_server_is_down(self):
        client = MLXClient("lmstudio:ornith-1.5-9b")
        with patch.object(client, "check_lmstudio", return_value={"available": False, "model_loaded": False, "models": [], "error": "refused"}):
            with self.assertRaisesRegex(RuntimeError, "LM Studio is not running"):
                list(client.generate_stream("lmstudio:ornith-1.5-9b", "prompt"))

    def test_local_model_mode_sets_offline_environment_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(_configure_local_model_mode())
            self.assertEqual(os.environ["HF_HUB_OFFLINE"], "1")
            self.assertEqual(os.environ["TRANSFORMERS_OFFLINE"], "1")

    def test_model_download_opt_in_leaves_offline_flags_unset(self):
        with patch.dict(os.environ, {"GRAVEDANCER_ALLOW_MODEL_DOWNLOADS": "1"}, clear=True):
            self.assertFalse(_configure_local_model_mode())
            self.assertNotIn("HF_HUB_OFFLINE", os.environ)

    def test_model_cache_keeps_only_one_loaded_model(self):
        client = MLXClient("mlx-community/example")

        with patch.object(client, "_is_mlx_vlm_model", return_value=False):
            with patch("mlx_lm.load", side_effect=lambda name: (f"model:{name}", "tokenizer")) as load:
                first = client._load_model("mlx-community/first")
                self.assertEqual(first, ("mlx_lm", "model:mlx-community/first", "tokenizer"))
                # Single-slot cache: any later request reuses the held slot
                # instead of keeping a second model resident.
                again = client._load_model("mlx-community/second")
                self.assertIs(again, first)
                self.assertEqual(load.call_count, 1)
                client.release_loaded_model()
                self.assertIsNone(client._loaded_model)

    def test_switching_models_releases_previous_model_before_load(self):
        client = MLXClient("mlx-community/first")
        loaded = {
            "mlx-community/first": ("first-model", "first-tokenizer"),
            "mlx-community/second": ("second-model", "second-tokenizer"),
        }
        with patch.object(client, "_load_model", side_effect=lambda name: loaded[name]) as load:
            with patch.object(client, "release_loaded_model", wraps=client.release_loaded_model) as release:
                client._ensure_model_loaded("mlx-community/first")
                client._ensure_model_loaded("mlx-community/second")

        release.assert_called_once()
        self.assertEqual(load.call_count, 2)
        self.assertEqual(client._active_model, "mlx-community/second")

    def test_model_availability_accepts_local_paths_and_cached_repo_ids(self):
        client = MLXClient()
        with tempfile.TemporaryDirectory() as model_dir:
            self.assertTrue(client.is_model_available_locally(model_dir))

        with patch("src.utils.mlx_client.list_local_mlx_models", return_value=[("Cached", "mlx-community/cached")]):
            self.assertTrue(client.is_model_available_locally("mlx-community/cached"))
            self.assertFalse(client.is_model_available_locally("mlx-community/missing"))

    def test_bonsai_runtime_support_requires_1bit_quantization(self):
        client = MLXClient(BONSAI_1BIT_MODEL)

        with patch("src.utils.mlx_client._bonsai_runtime_python", return_value=Path("/opt/bonsai/python")), \
             patch.object(Path, "is_file", return_value=True), \
             patch("src.utils.mlx_client.subprocess.run", return_value=SimpleNamespace(returncode=1)):
            self.assertFalse(client.is_model_supported_by_runtime())

    def test_bonsai_command_uses_isolated_runtime(self):
        client = MLXClient(BONSAI_1BIT_MODEL)
        with patch("src.utils.mlx_client._bonsai_runtime_python", return_value=Path("/opt/bonsai/python")), \
             patch.object(Path, "is_file", return_value=True):
            command = client._bonsai_command()

        self.assertEqual(command[:2], ["/opt/bonsai/python", "-u"])

    def test_normal_models_do_not_require_bonsai_runtime(self):
        self.assertTrue(MLXClient("mlx-community/example").is_model_supported_by_runtime())

    def test_disables_thinking_when_the_template_supports_it(self):
        class Tokenizer:
            def apply_chat_template(self, messages, **kwargs):
                self.messages = messages
                self.kwargs = kwargs
                return "formatted"

        tokenizer = Tokenizer()

        self.assertEqual(_apply_chat_template(tokenizer, "Prompt", "System"), "formatted")
        self.assertFalse(tokenizer.kwargs["enable_thinking"])

    def test_falls_back_for_templates_without_thinking_control(self):
        class Tokenizer:
            def apply_chat_template(self, messages, **kwargs):
                if "enable_thinking" in kwargs:
                    raise TypeError("unsupported keyword")
                self.kwargs = kwargs
                return "formatted"

        tokenizer = Tokenizer()

        self.assertEqual(_apply_chat_template(tokenizer, "Prompt"), "formatted")
        self.assertNotIn("enable_thinking", tokenizer.kwargs)

    def test_subprocess_command_keeps_the_model_flag_and_value_in_order(self):
        client = MLXClient("mlx-community/example")

        command = client._mlx_command("story prompt", system="system prompt", model="mlx-community/other")

        self.assertEqual(command[command.index("--model") + 1], "mlx-community/other")
        self.assertEqual(command[command.index("--prompt") + 1], "story prompt")

    def test_subprocess_logging_redacts_prompt_content(self):
        rendered = _redact_command_arguments([
            "python", "-m", "mlx_lm.generate", "--prompt", "private story", "--system", "private system",
        ])

        self.assertNotIn("private story", rendered)
        self.assertNotIn("private system", rendered)
        self.assertEqual(rendered.count("<redacted>"), 2)

    def test_lmstudio_stream_yields_sse_content_deltas(self):
        client = MLXClient("lmstudio:ornith-1.5-9b")

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def __iter__(self):
                return iter([
                    b'data: {"choices":[{"delta":{"content":"Ash"}}]}\n',
                    b'data: {"choices":[{"delta":{"content":" and bone"}}]}\n',
                    b'data: [DONE]\n',
                ])

        with patch("src.utils.mlx_client.urllib.request.urlopen", return_value=Response()):
            result = list(client._generate_lmstudio_stream(
                "lmstudio:ornith-1.5-9b", "prompt", None, 0.7, 0.9, 6000
            ))

        self.assertEqual(result, ["Ash", " and bone"])

    def test_lmstudio_stream_uses_configured_token_ceiling(self):
        client = MLXClient("lmstudio:ornith-1.5-9b")
        captured = {}

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def __iter__(self):
                return iter([b'data: [DONE]\n'])

        def fake_urlopen(request, timeout):
            captured["payload"] = json.loads(request.data)
            return Response()

        with patch("src.utils.mlx_client.urllib.request.urlopen", side_effect=fake_urlopen):
            list(client._generate_lmstudio_stream(
                "lmstudio:ornith-1.5-9b", "prompt", None, 0.7, 0.9, 6000
            ))

        self.assertEqual(captured["payload"]["max_tokens"], 6000)
        self.assertTrue(captured["payload"]["stream"])

    def test_lmstudio_stream_filters_reasoning_tags_split_across_chunks(self):
        client = MLXClient("lmstudio:ornith-1.5-9b")

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def __iter__(self):
                return iter([
                    b'data: {"choices":[{"delta":{"content":"<thi"}}]}\n',
                    b'data: {"choices":[{"delta":{"content":"nk>private"}}]}\n',
                    b'data: {"choices":[{"delta":{"content":"</think>Visible"}}]}\n',
                    b'data: [DONE]\n',
                ])

        with patch("src.utils.mlx_client.urllib.request.urlopen", return_value=Response()):
            result = "".join(client._generate_lmstudio_stream(
                "lmstudio:ornith-1.5-9b", "prompt", None, 0.7, 0.9, 6000
            ))

        self.assertEqual(result, "Visible")
