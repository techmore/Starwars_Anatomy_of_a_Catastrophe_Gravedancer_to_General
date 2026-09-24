"""Draw Things API and local-CLI clients.

Draw Things exposes an Automatic1111-compatible HTTP server when you enable
its API Server (Draw Things → Settings → API Server). We talk to it via the
standard /sdapi/v1 endpoints, so the same client drives:

  * Flux.2 Klein 4b   -> txt2img for keyframe images
  * Wan 2.2 ...        -> img2img for image-to-video clips (best-effort)

Design notes:
  - Images come back as base64 PNG in the ``images`` array (txt2img) or
    ``images``/``videos`` depending on model. We decode to raw bytes.
  - Video (Wan I2V) responses are less standardised; ``generate_video`` returns
    a dict that may contain ``video_bytes`` or ``error`` so callers can fall
    back to a manual paste workflow.
  - Port auto-probing happens in the sidebar UI; the API client just talks to
    whatever base_url it's given.
  - Set ``GRAVEDANCER_DT_BACKEND=cli`` to use the installed
    ``draw-things-cli`` binary without a running API server.
  - Set ``GRAVEDANCER_DT_BACKEND=comfyui`` to use a headless ComfyUI server
    with an API-format workflow and the same byte-oriented image interface.
"""

import base64
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

# Ports Draw Things is known to use. Sidebar probes these in order.
DEFAULT_DT_PORTS: tuple[int, ...] = (7860, 7859, 7001)
DEFAULT_DT_CLI_MODEL = "flux_2_klein_9b_i8x.ckpt"


def _requests():
    import requests

    return requests


class DrawThingsClient:
    backend = "api"

    def __init__(self, base_url: str = "http://localhost:7860"):
        self.base_url = base_url.rstrip("/")
        self.api_root = f"{self.base_url}/sdapi/v1"
        self.txt2img = f"{self.api_root}/txt2img"
        self.img2img = f"{self.api_root}/img2img"
        self.options = f"{self.api_root}/options"
        self.samplers = f"{self.api_root}/samplers"
        self.models = f"{self.api_root}/sd-models"

    # ----- low-level helpers -------------------------------------------------

    def _request(self, method: str, url: str, **kwargs):
        """HTTP request with retries limited to connection-level failures.

        Timed-out requests are never retried: a slow-but-successful generation
        render would otherwise be issued a second time.
        """
        requests = _requests()
        timeout = kwargs.pop("timeout", 300)
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                return requests.request(method, url, timeout=timeout, **kwargs)
            except requests.exceptions.ConnectionError as e:
                last_err = e
                if attempt < 2:
                    time.sleep(1.0)
        assert last_err is not None
        raise last_err

    # ----- connection / models ----------------------------------------------

    def check_connection(self) -> bool:
        try:
            r = self._request("GET", self.options, timeout=4)
            return r.status_code == 200
        except Exception:
            return False

    def get_options(self) -> dict[str, Any]:
        r = self._request("GET", self.options, timeout=5)
        r.raise_for_status()
        return r.json()

    def current_model_name(self) -> str:
        """Return the currently-loaded model title, or '' if unknown."""
        try:
            opts = self.get_options()
            return opts.get("sd_model_checkpoint") or opts.get("model") or ""
        except Exception:
            return ""

    def list_models(self) -> list[str]:
        """Return available model titles. Returns [] if the endpoint is missing."""
        try:
            r = self._request("GET", self.models, timeout=5)
            if r.status_code != 200:
                return []
            data = r.json()
            if isinstance(data, list):
                # A1111 returns list of {"title","model_name"}, DT may differ.
                return [m.get("title") or m.get("model_name") or str(m) for m in data] if data and isinstance(data[0], dict) else [str(m) for m in data]
        except Exception:
            pass
        return []

    def switch_model(self, name_hint: str) -> bool:
        """Switch to the first model whose title contains ``name_hint``.

        Draw Things' A1111-compat layer usually honours ``sd_model_checkpoint``.
        Returns True if a matching model was found and posted.
        """
        models = self.list_models()
        match = next((m for m in models if name_hint.lower() in str(m).lower()), None)
        if not match:
            return False
        try:
            response = self._request("POST", self.options, json={"sd_model_checkpoint": match}, timeout=30)
            response.raise_for_status()
            return True
        except Exception:
            return False

    # ----- generation --------------------------------------------------------

    def generate_image(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 576,
        steps: int = 5,
        cfg: float = 1.4,
        sampler: str = "DDIM Trailing",
        seed: int = -1,
        extra: dict[str, Any] | None = None,
    ) -> bytes:
        """Generate a keyframe image via Flux.2 Klein 9B distilled. Returns PNG bytes."""
        payload: dict[str, Any] = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "width": width,
            "height": height,
            "steps": steps,
            "cfg_scale": cfg,
            "sampler_name": sampler,
            "seed": seed,
            "batch_size": 1,
            "n_iter": 1,
            # Draw Things performance/quality options for Flux.2 Klein
            # distilled on Apple Silicon (M1 Pro 32GB verified):
            "tea_cache": True,               # step caching: big speedup
            "tea_cache_threshold": 0.15,     # strict = better quality
            "tea_cache_start": 2,
            "tea_cache_max_skip_steps": 2,   # conservative skipping
        }
        if extra:
            payload.update(extra)

        r = self._request("POST", self.txt2img, json=payload, timeout=600)
        r.raise_for_status()
        data = r.json()

        # A1111-compatible: {"images": ["<b64 png>", ...]}
        images = data.get("images") or []
        if images:
            return base64.b64decode(images[0])

        # Some DT responses nest differently — try a couple of fallbacks.
        if isinstance(data.get("image"), str):
            return base64.b64decode(data["image"])

        raise RuntimeError(f"Draw Things returned no image. Keys: {list(data.keys())}")

    def generate_video(
        self,
        init_image_bytes: bytes,
        prompt: str,
        negative_prompt: str = "",
        width: int = 832,
        height: int = 480,
        steps: int = 25,
        cfg: float = 7.0,
        seed: int = -1,
        sampler: str = "Euler",
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Attempt an image-to-video clip via Wan 2.2.

        Draw Things' I2V response shape is not standardised. This returns a dict
        with either ``video_bytes`` (success) or ``fallback`` + ``info`` (caller
        should fall back to showing the keyframe + motion prompt for manual use).
        """
        init_b64 = base64.b64encode(init_image_bytes).decode("ascii")
        payload: dict[str, Any] = {
            "init_images": [init_b64],
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "width": width,
            "height": height,
            "steps": steps,
            "cfg_scale": cfg,
            "sampler_name": sampler,
            "seed": seed,
            "batch_size": 1,
            "n_iter": 1,
        }
        if extra:
            payload.update(extra)

        try:
            r = self._request("POST", self.img2img, json=payload, timeout=900)
            r.raise_for_status()
            data = r.json()

            # Try every known/likely field where a video blob could land.
            for key in ("videos", "video", "images", "image", "data"):
                blob = data.get(key)
                if not blob:
                    continue
                if isinstance(blob, list) and blob:
                    blob = blob[0]
                if isinstance(blob, str) and len(blob) > 256:  # plausible base64
                    try:
                        decoded = base64.b64decode(blob)
                        # Heuristic: mp4/webm/gif magic bytes, else assume it's an image fallback.
                        if decoded[:4] in (b"\x00\x00\x00\x18", b"\x1a\x45\xdf\xa3", b"GIF8"):
                            return {"video_bytes": decoded, "raw": data}
                        # If it looks like a PNG/WebP still, surface as fallback image.
                        if decoded[:8] == b"\x89PNG\r\n\x1a\n" or decoded[:4] == b"RIFF":
                            return {"fallback_image": decoded, "info": "Draw Things returned a still frame, not a video clip.", "raw": data}
                    except Exception:
                        continue

            # Response parsed but no recognisable media.
            return {
                "fallback": True,
                "info": f"No video bytes in response. Keys: {list(data.keys())}",
                "raw": data,
            }
        except Exception as e:
            return {"fallback": True, "info": f"Video generation call failed: {e}", "raw": {}}


class DrawThingsCliClient:
    """Draw Things client backed by the installed ``draw-things-cli`` binary.

    The CLI writes media to a path instead of returning A1111-compatible
    base64 JSON, so this adapter keeps the same byte-oriented interface used
    by the image phase while avoiding a running Draw Things API server.
    """

    backend = "cli"

    def __init__(
        self,
        model: str | None = None,
        binary: str | None = None,
        models_dir: str | None = None,
    ):
        self.binary = (
            binary
            or os.environ.get("GRAVEDANCER_DT_CLI_BIN", "draw-things-cli").strip()
            or "draw-things-cli"
        )
        self.model = (
            model
            or os.environ.get("GRAVEDANCER_DT_CLI_MODEL", DEFAULT_DT_CLI_MODEL).strip()
            or DEFAULT_DT_CLI_MODEL
        )
        self.models_dir = models_dir or os.environ.get("DRAWTHINGS_MODELS_DIR", "").strip()

    def _command_available(self) -> bool:
        return bool(shutil.which(self.binary) or Path(self.binary).is_file())

    def _run(self, args: list[str], timeout: int = 900) -> subprocess.CompletedProcess[str]:
        if not self._command_available():
            raise RuntimeError(
                f"Draw Things CLI not found: {self.binary}. "
                "Set GRAVEDANCER_DT_CLI_BIN or install draw-things-cli."
            )
        try:
            return subprocess.run(
                [self.binary, *args],
                check=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"Draw Things CLI timed out after {timeout}s") from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or "").strip()
            raise RuntimeError(
                f"Draw Things CLI failed (exit {exc.returncode})"
                + (f": {detail[-2000:]}" if detail else "")
            ) from exc

    def _model_args(self) -> list[str]:
        args = ["--model", self.model]
        if self.models_dir:
            args.extend(["--models-dir", self.models_dir])
        return args

    def _offline_args(self) -> list[str]:
        if os.environ.get("GRAVEDANCER_DT_CLI_ALLOW_DOWNLOADS") == "1":
            return []
        return ["--offline", "--no-download-missing"]

    def check_connection(self) -> bool:
        """Return whether the CLI binary is available without spawning it."""
        return self._command_available()

    def get_options(self) -> dict[str, Any]:
        return {"backend": self.backend, "model": self.model, "binary": self.binary}

    def current_model_name(self) -> str:
        return self.model

    def list_models(self) -> list[str]:
        """Return downloaded model file ids reported by the CLI."""
        try:
            result = self._run(
                ["models", "list", "--downloaded-only", "--offline"]
                + (["--models-dir", self.models_dir] if self.models_dir else []),
                timeout=30,
            )
        except Exception:
            return []
        models: list[str] = []
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith(("Models directory:", "MODEL ")):
                continue
            model_id = stripped.split()[0]
            if model_id.endswith((".ckpt", ".safetensors")):
                models.append(model_id)
        return models

    def switch_model(self, name_hint: str) -> bool:
        """Switch the model used by subsequent CLI calls in this client."""
        match = next(
            (model for model in self.list_models() if name_hint.lower() in model.lower()),
            None,
        )
        if not match:
            return False
        self.model = match
        return True

    def _write_prompt_file(self, directory: str, name: str, text: str) -> str:
        path = Path(directory) / name
        path.write_text(text or "", encoding="utf-8")
        return str(path)

    def generate_image(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 576,
        steps: int = 5,
        cfg: float = 1.4,
        sampler: str = "DDIM Trailing",
        seed: int = -1,
        extra: dict[str, Any] | None = None,
    ) -> bytes:
        """Generate a PNG through the local CLI and return its bytes."""
        del sampler  # CLI resolves sampler/settings from model recommendations.
        with tempfile.TemporaryDirectory(prefix="gravedancer-drawthings-") as directory:
            output_path = Path(directory) / "generated.png"
            args = [
                "generate",
                *self._model_args(),
                "--prompt-file",
                self._write_prompt_file(directory, "prompt.txt", prompt),
                "--width",
                str(width),
                "--height",
                str(height),
                "--steps",
                str(steps),
                "--cfg",
                str(cfg),
                "--seed",
                str(seed),
                "--disable-preview",
                "--output",
                str(output_path),
            ]
            loras: Any = extra.get("loras") if isinstance(extra, dict) else None
            if loras is None:
                raw_loras = os.environ.get("GRAVEDANCER_DT_CLI_LORAS_JSON", "").strip()
                if raw_loras:
                    try:
                        loras = json.loads(raw_loras)
                    except json.JSONDecodeError as exc:
                        raise RuntimeError("GRAVEDANCER_DT_CLI_LORAS_JSON is invalid") from exc
            if isinstance(loras, list) and loras:
                args.extend(["--config-json", json.dumps({"loras": loras}, separators=(",", ":"))])
            args.extend(self._offline_args())
            if negative_prompt:
                args.extend([
                    "--negative-prompt-file",
                    self._write_prompt_file(directory, "negative-prompt.txt", negative_prompt),
                ])
            self._run(args)
            if not output_path.is_file():
                raise RuntimeError("Draw Things CLI completed without writing a PNG")
            return output_path.read_bytes()

    def generate_video(
        self,
        init_image_bytes: bytes,
        prompt: str,
        negative_prompt: str = "",
        width: int = 832,
        height: int = 480,
        steps: int = 25,
        cfg: float = 7.0,
        seed: int = -1,
        sampler: str = "Euler",
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate an MP4 through the CLI, when a video model is configured."""
        del sampler, extra
        video_model = os.environ.get("GRAVEDANCER_DT_CLI_VIDEO_MODEL", self.model).strip() or self.model
        frames = os.environ.get("GRAVEDANCER_DT_CLI_FRAMES", "49")
        with tempfile.TemporaryDirectory(prefix="gravedancer-drawthings-") as directory:
            init_path = Path(directory) / "init.png"
            output_path = Path(directory) / "generated.mp4"
            init_path.write_bytes(init_image_bytes)
            args = [
                "generate",
                "--model",
                video_model,
                "--prompt-file",
                self._write_prompt_file(directory, "prompt.txt", prompt),
                "--negative-prompt-file",
                self._write_prompt_file(directory, "negative-prompt.txt", negative_prompt),
                "--image",
                str(init_path),
                "--width",
                str(width),
                "--height",
                str(height),
                "--frames",
                str(frames),
                "--steps",
                str(steps),
                "--cfg",
                str(cfg),
                "--seed",
                str(seed),
                "--disable-preview",
                "--output",
                str(output_path),
                *self._offline_args(),
            ]
            try:
                self._run(args, timeout=1800)
                if not output_path.is_file():
                    return {"fallback": True, "info": "Draw Things CLI completed without writing a video."}
                return {"video_bytes": output_path.read_bytes(), "raw": {}}
            except Exception as exc:
                return {"fallback": True, "info": f"Draw Things CLI video generation failed: {exc}", "raw": {}}


def get_drawthings_client(
    base_url: str | None = None,
) -> DrawThingsClient | DrawThingsCliClient:
    """Create a Draw Things API, Draw Things CLI, or ComfyUI client."""
    backend = os.environ.get("GRAVEDANCER_DT_BACKEND", "api").strip().lower()
    if backend in {"comfy", "comfyui", "comfy-ui"} or str(base_url or "").strip().lower() in {
        "comfy",
        "comfyui",
        "comfy-ui",
    }:
        from src.utils.comfyui_client import ComfyUIClient

        candidate_url = base_url if str(base_url or "").strip().lower() not in {
            "comfy",
            "comfyui",
            "comfy-ui",
        } else None
        return ComfyUIClient(candidate_url)
    if backend in {"cli", "local-cli", "draw-things-cli"} or str(base_url or "").strip().lower() in {"cli", "draw-things-cli"}:
        return DrawThingsCliClient()
    if base_url:
        return DrawThingsClient(base_url)
    env_url = os.environ.get("GRAVEDANCER_DT_URL", "").strip()
    if env_url:
        return DrawThingsClient(env_url)
    for port in DEFAULT_DT_PORTS:
        candidate = f"http://localhost:{port}"
        try:
            client = DrawThingsClient(candidate)
            if client.check_connection():
                return client
        except Exception:
            continue
    # Fall back to the first known port; calls will surface the error.
    return DrawThingsClient(f"http://localhost:{DEFAULT_DT_PORTS[0]}")
