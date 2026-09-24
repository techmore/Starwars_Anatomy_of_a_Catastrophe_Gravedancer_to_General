import json
import unittest
from unittest.mock import Mock, patch

from src.utils.comfyui_client import ComfyUIClient
from src.utils.drawthings_client import get_drawthings_client


WORKFLOW = {
    "1": {
        "class_type": "TestNode",
        "inputs": {
            "prompt": "{{prompt}}",
            "negative": "{{negative_prompt}}",
            "seed": "{{seed}}",
            "width": "{{width}}",
            "cfg": "{{cfg}}",
            "model": "{{model}}",
        },
    }
}


class TestComfyUIClient(unittest.TestCase):
    def test_workflow_placeholders_are_submitted_and_image_is_downloaded(self):
        prompt_response = Mock(status_code=200)
        prompt_response.json.return_value = {"prompt_id": "abc123"}
        history_response = Mock(status_code=200)
        history_response.json.return_value = {
            "abc123": {
                "status": {"status_str": "success", "completed": True},
                "outputs": {
                    "9": {
                        "images": [
                            {"filename": "gravedancer_00001.png", "subfolder": "", "type": "output"}
                        ]
                    }
                },
            }
        }
        image_response = Mock(status_code=200, content=b"\x89PNG\r\n\x1a\nfake")
        client = ComfyUIClient(
            base_url="http://127.0.0.1:8188",
            workflow=WORKFLOW,
            model="checkpoint.safetensors",
            poll_interval=0,
        )

        with patch.object(
            client,
            "_request",
            side_effect=[prompt_response, history_response, image_response],
        ) as request:
            result = client.generate_image(
                prompt="a lighthouse",
                negative_prompt="text",
                width=640,
                height=360,
                steps=7,
                cfg=5.5,
                seed=42,
            )

        self.assertEqual(result, image_response.content)
        submitted = request.call_args_list[0].kwargs["json"]["prompt"]
        inputs = submitted["1"]["inputs"]
        self.assertEqual(inputs["prompt"], "a lighthouse")
        self.assertEqual(inputs["negative"], "text")
        self.assertEqual(inputs["seed"], 42)
        self.assertEqual(inputs["width"], 640)
        self.assertEqual(inputs["cfg"], 5.5)
        self.assertEqual(inputs["model"], "checkpoint.safetensors")
        self.assertEqual(request.call_args_list[2].kwargs["params"]["filename"], "gravedancer_00001.png")

    def test_regular_editor_workflow_is_rejected(self):
        client = ComfyUIClient(workflow={"nodes": [], "links": []})
        with self.assertRaisesRegex(RuntimeError, "API-format"):
            client.generate_image(prompt="test")

    def test_missing_model_is_actionable_for_template_workflow(self):
        client = ComfyUIClient(workflow=WORKFLOW, model="")
        with self.assertRaisesRegex(RuntimeError, "GRAVEDANCER_COMFYUI_MODEL"):
            client.generate_image(prompt="test")

    @patch.dict("os.environ", {"GRAVEDANCER_DT_BACKEND": "comfyui"}, clear=False)
    def test_backend_selection_uses_comfyui(self):
        client = get_drawthings_client("http://127.0.0.1:8188")
        self.assertIsInstance(client, ComfyUIClient)


if __name__ == "__main__":
    unittest.main()
