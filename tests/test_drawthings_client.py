import base64
import json
import os
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from src.utils.drawthings_client import DrawThingsCliClient, DrawThingsClient, get_drawthings_client


class TestDrawThingsClient(unittest.TestCase):
    @patch("src.utils.drawthings_client.time.sleep")
    @patch("src.utils.drawthings_client._requests")
    def test_request_reuses_timeout_across_retries(self, requests_factory, sleep):
        requests = Mock()
        requests.exceptions.ConnectionError = ConnectionError
        requests.exceptions.Timeout = TimeoutError
        response = Mock()
        requests.request.side_effect = [ConnectionError("offline"), response]
        requests_factory.return_value = requests

        client = DrawThingsClient()
        self.assertIs(client._request("GET", client.options, timeout=7), response)

        self.assertEqual(requests.request.call_args_list[0].kwargs["timeout"], 7)
        self.assertEqual(requests.request.call_args_list[1].kwargs["timeout"], 7)
        sleep.assert_called_once()

    def test_generate_image_decodes_base64_image(self):
        png_bytes = b"\x89PNG\r\n\x1a\nfakepng"
        encoded = base64.b64encode(png_bytes).decode("ascii")
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"images": [encoded]}

        client = DrawThingsClient("http://localhost:7860")
        with patch.object(client, "_request", return_value=response) as request_mock:
            out = client.generate_image(prompt="A test prompt")

        self.assertEqual(out, png_bytes)
        request_mock.assert_called_once()

    def test_generate_video_returns_fallback_for_still_frame(self):
        still_bytes = b"\x89PNG\r\n\x1a\n" + (b"still-frame-bytes" * 20)
        encoded = base64.b64encode(still_bytes).decode("ascii")
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"images": [encoded]}

        client = DrawThingsClient("http://localhost:7860")
        with patch.object(client, "_request", return_value=response) as request_mock:
            out = client.generate_video(
                init_image_bytes=b"keyframe-bytes",
                prompt="A motion prompt",
            )

        self.assertIn("fallback_image", out)
        self.assertIn("still frame", out["info"])
        self.assertEqual(out["fallback_image"], still_bytes)
        request_mock.assert_called_once()

    def test_generate_video_returns_fallback_on_empty_response(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"status": "ok"}

        client = DrawThingsClient("http://localhost:7860")
        with patch.object(client, "_request", return_value=response):
            out = client.generate_video(
                init_image_bytes=b"keyframe-bytes",
                prompt="A motion prompt",
            )

        self.assertTrue(out["fallback"])
        self.assertIn("No video bytes", out["info"])


class TestDrawThingsCliClient(unittest.TestCase):
    def test_cli_reports_installed_binary_without_starting_generation(self):
        client = DrawThingsCliClient(binary="draw-things-cli")
        with patch("src.utils.drawthings_client.shutil.which", return_value="/usr/local/bin/draw-things-cli"):
            self.assertTrue(client.check_connection())

    def test_cli_generation_reads_png_written_to_output_path(self):
        png_bytes = b"\x89PNG\r\n\x1a\ncli-png"
        client = DrawThingsCliClient(model="flux_1_schnell_q5p.ckpt")

        def fake_run(args, timeout=900):
            del timeout
            output_path = Path(args[args.index("--output") + 1])
            output_path.write_bytes(png_bytes)
            return Mock(stdout="", stderr="")

        with patch.object(client, "_run", side_effect=fake_run) as run:
            self.assertEqual(
                client.generate_image(
                    prompt="A lighthouse",
                    negative_prompt="text",
                    width=1024,
                    height=1024,
                    steps=4,
                    seed=42,
                ),
                png_bytes,
            )

        args = run.call_args.args[0]
        self.assertEqual(args[:3], ["generate", "--model", "flux_1_schnell_q5p.ckpt"])
        self.assertIn("--prompt-file", args)
        self.assertIn("--negative-prompt-file", args)
        self.assertIn("--disable-preview", args)
        self.assertIn("--no-download-missing", args)

    def test_cli_generation_passes_lora_configuration(self):
        png_bytes = b"\x89PNG\r\n\x1a\ncli-lora"
        client = DrawThingsCliClient(model="flux_1_schnell_q5p.ckpt")

        def fake_run(args, timeout=900):
            del timeout
            output_path = Path(args[args.index("--output") + 1])
            output_path.write_bytes(png_bytes)
            return Mock(stdout="", stderr="")

        with patch.object(client, "_run", side_effect=fake_run) as run:
            client.generate_image(
                prompt="A starship over a desert",
                extra={"loras": [{"file": "armor.safetensors", "weight": 0.65}]},
            )

        args = run.call_args.args[0]
        config = json.loads(args[args.index("--config-json") + 1])
        self.assertEqual(config["loras"][0]["file"], "armor.safetensors")
        self.assertEqual(config["loras"][0]["weight"], 0.65)

    def test_backend_selection_can_use_cli_without_an_api_server(self):
        with patch.dict(os.environ, {"GRAVEDANCER_DT_BACKEND": "cli"}):
            client = get_drawthings_client("http://localhost:7860")
        self.assertIsInstance(client, DrawThingsCliClient)
