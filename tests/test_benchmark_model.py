import unittest
from unittest.mock import patch

from scripts.benchmark_model import run_benchmark


class TestBenchmarkModel(unittest.TestCase):
    def test_run_benchmark_reports_stream_metrics_without_backend(self):
        class FakeClient:
            def __init__(self, model):
                self.model = model

            def generate_stream(self, **kwargs):
                yield "A small "
                yield "test passage."

        with patch("scripts.benchmark_model.MLXClient", FakeClient):
            report = run_benchmark("fake-model", 32, "Write a test.")

        self.assertTrue(report["success"])
        self.assertEqual(report["model"], "fake-model")
        self.assertEqual(report["characters"], len("A small test passage."))
        self.assertGreaterEqual(report["approx_tokens"], 1)
        self.assertGreaterEqual(report["total_seconds"], 0)


if __name__ == "__main__":
    unittest.main()
