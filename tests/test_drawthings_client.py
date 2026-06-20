import base64
import unittest
from unittest.mock import Mock, patch

from src.utils.drawthings_client import DrawThingsClient


class TestDrawThingsClient(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
