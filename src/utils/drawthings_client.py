"""Draw Things local API client.

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
  - Port auto-probing happens in the sidebar UI; this client just talks to
    whatever base_url it's given.
"""

import base64
import time
import io
from typing import Dict, Any, Optional, List, Tuple

try:
    import streamlit as st
except ModuleNotFoundError:  # pragma: no cover - allows headless tests
    class _StreamlitFallback:
        @staticmethod
        def cache_resource(func=None):
            if func is None:
                def decorator(inner):
                    return inner
                return decorator
            return func

    st = _StreamlitFallback()

# Ports Draw Things is known to use. Sidebar probes these in order.
DEFAULT_DT_PORTS: Tuple[int, ...] = (7860, 7001)


def _requests():
    import requests

    return requests


class DrawThingsClient:
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
        """HTTP request with a couple of retries on transient connection errors."""
        requests = _requests()
        last_err: Optional[Exception] = None
        for attempt in range(3):
            try:
                return requests.request(method, url, timeout=kwargs.pop("timeout", 300), **kwargs)
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
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

    def get_options(self) -> Dict[str, Any]:
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

    def list_models(self) -> List[str]:
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
            self._request("POST", self.options, json={"sd_model_checkpoint": match}, timeout=30)
            return True
        except Exception:
            return False

    def list_samplers(self) -> List[str]:
        try:
            r = self._request("GET", self.samplers, timeout=5)
            if r.status_code != 200:
                return []
            data = r.json()
            return [s.get("name", str(s)) if isinstance(s, dict) else str(s) for s in data]
        except Exception:
            return []

    # ----- generation --------------------------------------------------------

    def generate_image(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1344,
        height: int = 768,
        steps: int = 25,
        cfg: float = 2.5,
        sampler: str = "Euler a",
        seed: int = -1,
        extra: Optional[Dict[str, Any]] = None,
    ) -> bytes:
        """Generate a keyframe image via Flux.2 Klein 4b. Returns PNG bytes."""
        payload: Dict[str, Any] = {
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
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Attempt an image-to-video clip via Wan 2.2.

        Draw Things' I2V response shape is not standardised. This returns a dict
        with either ``video_bytes`` (success) or ``fallback`` + ``info`` (caller
        should fall back to showing the keyframe + motion prompt for manual use).
        """
        init_b64 = base64.b64encode(init_image_bytes).decode("ascii")
        payload: Dict[str, Any] = {
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


@st.cache_resource
def get_drawthings_client(base_url: str = f"http://localhost:{DEFAULT_DT_PORTS[0]}") -> DrawThingsClient:
    """Cached singleton. Keyed on base_url so changing the URL rebuilds it."""
    return DrawThingsClient(base_url)
