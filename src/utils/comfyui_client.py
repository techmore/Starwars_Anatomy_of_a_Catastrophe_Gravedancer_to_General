"""Headless ComfyUI client for the generalized image-generation backend.

ComfyUI exposes a small HTTP API rather than a Draw Things-compatible
``/sdapi/v1`` surface.  This adapter keeps the image phase byte-oriented while
letting a pack provide a ComfyUI *API-format* workflow.  Workflows may contain
the following placeholders anywhere in their input values::

    {{prompt}} {{negative_prompt}} {{seed}} {{width}} {{height}}
    {{steps}} {{cfg}} {{model}}

The workflow is deliberately supplied by configuration instead of being
reconstructed from a UI export.  That makes the backend portable across SD 1.5,
SDXL, Flux, and custom node graphs without adding ComfyUI-specific nodes to
the story pack.
"""

from __future__ import annotations

import copy
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any


DEFAULT_COMFYUI_URL = "http://127.0.0.1:8188"
DEFAULT_COMFYUI_WORKFLOW = (
    Path(__file__).resolve().parents[2] / "config" / "comfyui" / "sd15-api.json"
)


def _requests():
    import requests

    return requests


class ComfyUIClient:
    """Generate PNGs through a local/headless ComfyUI server.

    The server can stay bound to localhost.  The runner talks to it over the
    loopback interface, so enabling this backend does not change Swartzit's
    production bind or expose another network service.
    """

    backend = "comfyui"

    def __init__(
        self,
        base_url: str | None = None,
        workflow: str | dict[str, Any] | None = None,
        model: str | None = None,
        timeout: int | None = None,
        poll_interval: float | None = None,
    ):
        self.base_url = (
            base_url
            or os.environ.get("GRAVEDANCER_COMFYUI_URL", "")
            or DEFAULT_COMFYUI_URL
        ).rstrip("/")
        self.workflow_source = (
            workflow
            if workflow is not None
            else os.environ.get("GRAVEDANCER_COMFYUI_WORKFLOW_JSON", "").strip()
            or str(DEFAULT_COMFYUI_WORKFLOW)
        )
        self.model = (
            model
            if model is not None
            else os.environ.get("GRAVEDANCER_COMFYUI_MODEL", "").strip()
        )
        self.timeout = int(
            timeout
            if timeout is not None
            else os.environ.get("GRAVEDANCER_COMFYUI_TIMEOUT", "1800")
        )
        self.poll_interval = float(
            poll_interval
            if poll_interval is not None
            else os.environ.get("GRAVEDANCER_COMFYUI_POLL_SECONDS", "1")
        )
        self.client_id = str(uuid.uuid4())

    @property
    def prompt_url(self) -> str:
        return f"{self.base_url}/prompt"

    def _request(self, method: str, path: str, **kwargs):
        requests = _requests()
        timeout = kwargs.pop("timeout", 30)
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        return requests.request(method, url, timeout=timeout, **kwargs)

    def check_connection(self) -> bool:
        try:
            response = self._request("GET", "/system_stats", timeout=5)
            return response.status_code == 200
        except Exception:
            return False

    def get_options(self) -> dict[str, Any]:
        response = self._request("GET", "/system_stats", timeout=5)
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {"response": payload}

    def current_model_name(self) -> str:
        return self.model

    def list_models(self) -> list[str]:
        """Return checkpoint choices advertised by ComfyUI's object info."""
        try:
            response = self._request("GET", "/object_info", timeout=10)
            if response.status_code != 200:
                return []
            payload = response.json()
            node = payload.get("CheckpointLoaderSimple", {})
            choices = (
                node.get("input", {})
                .get("required", {})
                .get("ckpt_name", [[]])[0]
            )
            return [str(item) for item in choices] if isinstance(choices, list) else []
        except Exception:
            return []

    def switch_model(self, name_hint: str) -> bool:
        match = next(
            (model for model in self.list_models() if name_hint.lower() in model.lower()),
            None,
        )
        if not match:
            return False
        self.model = match
        return True

    def _load_workflow(self, source: str | dict[str, Any] | None) -> dict[str, Any]:
        source = source if source is not None else self.workflow_source
        if isinstance(source, dict):
            workflow = copy.deepcopy(source)
        else:
            raw = str(source).strip()
            path = Path(raw).expanduser()
            if path.is_file():
                raw = path.read_text(encoding="utf-8")
            try:
                workflow = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    "ComfyUI workflow must be a JSON file, inline JSON, or API-format object"
                ) from exc
        if not isinstance(workflow, dict) or "nodes" in workflow:
            raise RuntimeError(
                "ComfyUI requires an API-format workflow export (node id -> inputs/class_type), "
                "not the regular UI workflow JSON"
            )
        if not workflow:
            raise RuntimeError("ComfyUI workflow is empty")
        return workflow

    @staticmethod
    def _replace_placeholders(value: Any, replacements: dict[str, Any]) -> Any:
        if isinstance(value, dict):
            return {
                key: ComfyUIClient._replace_placeholders(item, replacements)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [
                ComfyUIClient._replace_placeholders(item, replacements)
                for item in value
            ]
        if not isinstance(value, str):
            return value
        if value in replacements:
            return replacements[value]
        result = value
        for token, replacement in replacements.items():
            result = result.replace(token, str(replacement))
        return result

    @staticmethod
    def _response_error(response, context: str) -> RuntimeError:
        detail = getattr(response, "text", "") or ""
        return RuntimeError(f"{context} (HTTP {response.status_code}): {detail[:2000]}")

    def _wait_for_history(self, prompt_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            response = self._request("GET", f"/history/{prompt_id}", timeout=10)
            if response.status_code == 200:
                payload = response.json()
                entry = payload.get(prompt_id) if isinstance(payload, dict) else None
                if entry is None and isinstance(payload, dict) and "outputs" in payload:
                    entry = payload
                if isinstance(entry, dict):
                    status = entry.get("status") or {}
                    status_name = str(status.get("status_str", "")).lower()
                    if status_name in {"error", "execution_error"}:
                        messages = status.get("messages") or status.get("message") or status
                        raise RuntimeError(f"ComfyUI execution failed: {messages}")
                    if isinstance(entry.get("outputs"), dict):
                        return entry
            time.sleep(max(0.05, self.poll_interval))
        raise RuntimeError(f"ComfyUI timed out after {self.timeout}s (prompt {prompt_id})")

    def _download_first_image(self, history: dict[str, Any]) -> bytes:
        outputs = history.get("outputs") or {}
        for node_output in outputs.values():
            if not isinstance(node_output, dict):
                continue
            for image in node_output.get("images") or []:
                if not isinstance(image, dict) or not image.get("filename"):
                    continue
                response = self._request(
                    "GET",
                    "/view",
                    params={
                        "filename": image["filename"],
                        "subfolder": image.get("subfolder", ""),
                        "type": image.get("type", "output"),
                    },
                    timeout=60,
                )
                if response.status_code != 200:
                    raise self._response_error(response, "ComfyUI image download failed")
                if response.content:
                    return response.content
        raise RuntimeError("ComfyUI completed without an image output")

    def generate_image(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 576,
        steps: int = 5,
        cfg: float = 1.4,
        sampler: str = "euler",
        seed: int = -1,
        extra: dict[str, Any] | None = None,
    ) -> bytes:
        extra = extra or {}
        workflow_source = extra.get("workflow") or extra.get("workflow_json")
        workflow = self._load_workflow(workflow_source)
        model = str(extra.get("model") or self.model).strip()
        replacements = {
            "{{prompt}}": prompt,
            "{{negative_prompt}}": negative_prompt,
            "{{seed}}": int(seed),
            "{{width}}": int(width),
            "{{height}}": int(height),
            "{{steps}}": int(steps),
            "{{cfg}}": float(cfg),
            "{{sampler}}": sampler,
            "{{model}}": model,
        }
        if "{{model}}" in json.dumps(workflow) and not model:
            raise RuntimeError(
                "ComfyUI workflow uses {{model}} but no checkpoint was configured; "
                "set draw_things.model or GRAVEDANCER_COMFYUI_MODEL"
            )
        workflow = self._replace_placeholders(workflow, replacements)

        response = self._request(
            "POST",
            "/prompt",
            json={"prompt": workflow, "client_id": self.client_id},
            timeout=30,
        )
        if response.status_code >= 400:
            raise self._response_error(response, "ComfyUI rejected the workflow")
        payload = response.json()
        prompt_id = payload.get("prompt_id") if isinstance(payload, dict) else None
        if not prompt_id:
            raise RuntimeError(f"ComfyUI response did not include prompt_id: {payload}")
        return self._download_first_image(self._wait_for_history(str(prompt_id)))

    def generate_video(self, *args, **kwargs) -> dict[str, Any]:
        del args, kwargs
        return {
            "fallback": True,
            "info": "The ComfyUI adapter currently supports image workflows only.",
        }

    def interrupt(self) -> bool:
        """Ask ComfyUI to interrupt its current graph, if one is running."""
        try:
            response = self._request("POST", "/interrupt", timeout=10)
            return response.status_code < 400
        except Exception:
            return False
