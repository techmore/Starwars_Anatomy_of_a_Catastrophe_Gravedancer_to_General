"""Tests for connect-retry behavior in the MLX client."""

import unittest
import urllib.error
from unittest.mock import Mock, patch

from src.utils.mlx_client import MLXClient, _urlopen_with_retries


class TestUrlopenRetries(unittest.TestCase):
    def _request(self):
        return urllib.request.Request("http://127.0.0.1:1234/v1/models")

    def test_retries_transient_failures_then_succeeds(self):
        response = Mock()
        outcomes = [
            urllib.error.URLError("refused"),
            urllib.error.URLError("reset"),
            response,
        ]
        with patch("src.utils.mlx_client.urllib.request.urlopen", side_effect=outcomes) as urlopen, \
             patch("src.utils.mlx_client.time.sleep") as sleep:
            result = _urlopen_with_retries(self._request(), timeout=5)
        self.assertIs(result, response)
        self.assertEqual(urlopen.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_http_error_is_not_retried(self):
        with patch(
            "src.utils.mlx_client.urllib.request.urlopen",
            side_effect=urllib.error.HTTPError("u", 404, "nf", None, None),
        ) as urlopen:
            with self.assertRaises(urllib.error.HTTPError):
                _urlopen_with_retries(self._request())
        self.assertEqual(urlopen.call_count, 1)

    def test_exhausted_retries_raise_last_error(self):
        with patch(
            "src.utils.mlx_client.urllib.request.urlopen",
            side_effect=urllib.error.URLError("down"),
        ), patch("src.utils.mlx_client.time.sleep"):
            with self.assertRaises(urllib.error.URLError):
                _urlopen_with_retries(self._request(), attempts=3)


class TestOpenCodeSpawnRetry(unittest.TestCase):
    def test_spawn_failure_retried_once(self):
        class FakeProc:
            def __init__(self):
                self.stdout = iter(['{"type":"text","part":{"text":"hi"}}'])
                self.stderr = Mock(read=Mock(return_value=""))
                self.wait = Mock(return_value=0)
                self.poll = Mock(return_value=0)

        client = MLXClient()
        good = FakeProc()
        with patch("src.utils.mlx_client.subprocess.Popen", side_effect=[OSError("boom"), good]) as popen, \
             patch("src.utils.mlx_client.time.sleep"):
            chunks = list(client._generate_opencode_stream(
                "opencode:x", "prompt", "system", max_tokens=16))
        self.assertEqual(popen.call_count, 2)
        self.assertEqual(chunks, ["hi"])

    def test_spawn_failure_twice_raises(self):
        client = MLXClient()
        with patch("src.utils.mlx_client.subprocess.Popen", side_effect=OSError("boom")), \
             patch("src.utils.mlx_client.time.sleep"):
            with self.assertRaisesRegex(RuntimeError, "Could not start OpenCode"):
                list(client._generate_opencode_stream(
                    "opencode:x", "prompt", "system", max_tokens=16))


if __name__ == "__main__":
    unittest.main()
