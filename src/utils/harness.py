"""Cross-platform inference-harness abstraction.

A "harness" is the backend that actually serves the selected model. The MLX
client already routes over HTTP for any model id with the ``lmstudio:`` prefix
(against ``GRAVEDANCER_LMSTUDIO_URL``) and falls back to in-process MLX for bare
model ids. This module turns that routing into an explicit, platform-aware
selection model so the Textual TUI can offer identical choices on macOS and
Linux:

    macOS:  rapid-mlx, LM Studio, Ollama (OpenAI-compatible HTTP), native MLX
    Linux:  Ollama, and any remote OpenAI-compatible endpoint
            (MLX/rapid-mlx/LM Studio are Apple-only)

Every HTTP harness speaks the same OpenAI-compatible surface, so a single
``lmstudio:<served-model-id>`` reference works for rapid-mlx, LM Studio, Ollama,
and a remote server hosted on an Ubuntu box. No MLX or Textual imports live in
this module so it stays importable on either platform.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from src.utils.models import format_model_label, list_local_mlx_models

_TIMEOUT = 5.0

# OpenCode CLI integration. The MLX client routes any ``opencode:<id>``
# reference through ``opencode run``, so this harness only has to discover
# model ids and map them to client-routable references.
OPENCODE_BIN = os.environ.get("GRAVEDANCER_OPENCODE_BIN", "opencode")
OXALPHA_FREE_ALIAS = "ox-alpha-free"
OXALPHA_FREE_TARGET_DEFAULT = "opencode/x-preview-f-free"


def resolve_oxalpha_target() -> str:
    """Resolve the real OpenCode model id behind the ox-alpha-free preset."""
    override = os.environ.get("GRAVEDANCER_OXALPHA_MODEL", "").strip()
    return override or OXALPHA_FREE_TARGET_DEFAULT


def detect_platform() -> str:
    """Return the normalized platform key (``darwin``, ``linux``, ``win32``)."""
    system = platform.system().lower()
    if system.startswith("darwin"):
        return "darwin"
    if system.startswith("linux"):
        return "linux"
    return system or "unknown"


_DARWIN = frozenset({"darwin"})
_DARWIN_LINUX = frozenset({"darwin", "linux"})
_DARWIN_WINDOWS = frozenset({"darwin", "win32"})


@dataclass(frozen=True)
class Harness:
    """A backend that can serve models for the pipeline.

    Attributes:
        id: stable identifier.
        name: human-readable label for the TUI.
        kind: ``"openai_http"`` or ``"mlx_native"``.
        default_base: server root (``http://host:port``) for HTTP harnesses.
        platforms: platform keys on which the harness is usable.
        note: one-line guidance shown in the TUI.
        env_url_override: env var that overrides ``default_base`` at runtime.
    """

    id: str
    name: str
    kind: str
    default_base: Optional[str]
    platforms: frozenset
    note: str = ""
    env_url_override: str = ""

    def base_url(self) -> str:
        """Resolve the server root, preferring the runtime env override."""
        if self.env_url_override:
            value = os.environ.get(self.env_url_override, "").strip()
            if value:
                return value.rstrip("/")
        if self.default_base:
            return self.default_base.rstrip("/")
        return ""

    def on_platform(self, platform_key: Optional[str] = None) -> bool:
        return (platform_key or detect_platform()) in self.platforms


HARNESSES: List[Harness] = [
    Harness(
        id="rapid-mlx",
        name="rapid-mlx",
        kind="openai_http",
        default_base="http://127.0.0.1:1234",
        platforms=_DARWIN,
        note="Apple Silicon only · MLX server with continuous batching & prefix cache",
        env_url_override="GRAVEDANCER_RAPIDMLX_URL",
    ),
    Harness(
        id="lm-studio",
        name="LM Studio",
        kind="openai_http",
        default_base="http://127.0.0.1:1234",
        platforms=_DARWIN_WINDOWS,
        note="OpenAI-compatible local server (not available on Linux)",
        env_url_override="GRAVEDANCER_LMSTUDIO_URL",
    ),
    Harness(
        id="ollama",
        name="Ollama",
        kind="openai_http",
        default_base="http://127.0.0.1:11434",
        platforms=_DARWIN_LINUX,
        note="macOS + Ubuntu — the natural cross-platform choice",
        env_url_override="GRAVEDANCER_OLLAMA_URL",
    ),
    Harness(
        id="remote-openai",
        name="Remote OpenAI endpoint",
        kind="openai_http",
        default_base=None,
        platforms=_DARWIN_LINUX,
        note="Any OpenAI-compatible server (vLLM / Ollama / LM Studio on another host)",
        env_url_override="GRAVEDANCER_LMSTUDIO_URL",
    ),
    Harness(
        id="opencode",
        name="OpenCode",
        kind="opencode_cli",
        default_base=None,
        platforms=_DARWIN_LINUX,
        note="opencode CLI · ox-alpha Free & 80+ hosted models — no local VRAM needed",
    ),
    Harness(
        id="native-mlx",
        name="Native MLX (in-process)",
        kind="mlx_native",
        default_base=None,
        platforms=_DARWIN,
        note="Apple-only · loads weights inside the app process",
    ),
]


def available_harnesses() -> List[Harness]:
    """Return harnesses usable on the current platform."""
    return [h for h in HARNESSES if h.on_platform()]


def by_id(harness_id: str) -> Harness:
    return next((h for h in HARNESSES if h.id == harness_id), HARNESSES[-1])


def _http_get_json(url: str, timeout: float = _TIMEOUT):
    request = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def resolve_base(harness: Harness, base: Optional[str] = None) -> str:
    """Resolve an explicit base URL, falling back to the harness default."""
    if base and base.strip():
        return base.strip().rstrip("/")
    return harness.base_url()


def list_served_models(harness: Harness, base: Optional[str] = None) -> List[str]:
    """List model ids served by an HTTP harness via ``GET /v1/models``."""
    if harness.kind != "openai_http":
        raise ValueError(f"{harness.id} is not an HTTP harness")
    root = resolve_base(harness, base)
    payload = _http_get_json(f"{root}/v1/models")
    ids: List[str] = []
    for item in payload.get("data", []):
        if isinstance(item, dict) and item.get("id"):
            ids.append(str(item["id"]))
    return sorted(set(ids))


def health_check(harness: Harness, base: Optional[str] = None) -> Dict[str, object]:
    """Probe ``/v1/models`` and report whether the harness is reachable."""
    if harness.kind == "opencode_cli":
        return opencode_health()
    if harness.kind != "openai_http":
        return {"ok": True, "available": True, "models": list_native_mlx_models(), "error": ""}
    root = resolve_base(harness, base)
    try:
        models = list_served_models(harness, base)
        return {"ok": True, "available": True, "models": models, "base": root, "error": ""}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return {"ok": False, "available": False, "models": [], "base": root, "error": str(exc)}


_MODEL_ROOTS = (
    Path(__file__).resolve().parents[2] / ".models",
    Path.home() / ".models",
)


def list_local_model_dirs() -> List[str]:
    """Scan repo-local and home model directories for loadable MLX checkpoints."""
    found: List[str] = []
    for root in _MODEL_ROOTS:
        if not root.is_dir():
            continue
        for entry in sorted(root.iterdir()):
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            has_config = (entry / "config.json").is_file()
            has_weights = any(entry.glob("*.safetensors"))
            if has_config and has_weights and entry.name not in found:
                found.append(entry.name)
    return sorted(found)


def list_native_mlx_models() -> List[str]:
    """Return model ids usable by native in-process MLX on macOS.

    Merges the Hugging Face cache scan (``models.py``) with repo-local and
    ``~/.models`` directories, deduplicated by repo id.
    """
    ids: List[str] = []
    try:
        ids.extend(repo for _label, repo in list_local_mlx_models())
    except Exception:
        pass
    ids.extend(list_local_model_dirs())
    seen: set[str] = set()
    unique: List[str] = []
    for model_id in ids:
        if model_id not in seen:
            seen.add(model_id)
            unique.append(model_id)
    return unique


def list_opencode_models() -> List[str]:
    """List model ids the ``opencode`` CLI can serve (``opencode models``)."""
    try:
        proc = subprocess.run(
            [OPENCODE_BIN, "models"],
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    ids = [
        line.strip() for line in proc.stdout.splitlines()
        if line.strip() and "/" in line
    ]
    return sorted(set(ids))


def list_opencode_model_choices() -> List[str]:
    """Curated OpenCode choices: ox-alpha preset, free tier, then everything else."""
    models = list_opencode_models()
    free = [m for m in models if m.endswith("-free")]
    rest = [m for m in models if not m.endswith("-free")]
    choices = [OXALPHA_FREE_ALIAS]
    choices.extend(free)
    choices.extend(rest)
    return choices


def opencode_health() -> Dict[str, object]:
    """Check the opencode binary and report its served models."""
    binary = shutil.which(OPENCODE_BIN)
    if not binary:
        return {
            "ok": False,
            "available": False,
            "models": [],
            "base": OPENCODE_BIN,
            "error": f"'{OPENCODE_BIN}' not found on PATH (install opencode or set GRAVEDANCER_OPENCODE_BIN)",
        }
    models = list_opencode_models()
    return {"ok": True, "available": True, "models": models, "base": binary, "error": ""}


def list_model_choices(harness: Harness, base: Optional[str] = None) -> List[str]:
    """Return display labels for every selectable model on a harness."""
    if harness.kind == "mlx_native":
        models = list_native_mlx_models()
        return [(format_model_label(m) or m) for m in models]
    if harness.kind == "opencode_cli":
        return list_opencode_model_choices()
    return list_served_models(harness, base)


def pipeline_model_ref(harness: Harness, model_id: str) -> str:
    """Return the client-routable model reference for a harness + model."""
    if harness.kind == "openai_http":
        return f"lmstudio:{model_id}"
    if harness.kind == "opencode_cli":
        if str(model_id) == OXALPHA_FREE_ALIAS:
            return f"opencode:{resolve_oxalpha_target()}"
        return f"opencode:{model_id}"
    return model_id


def pipeline_environment(harness: Harness, base: Optional[str] = None) -> Dict[str, str]:
    """Return the environment variables needed to route the pipeline to a harness."""
    env: Dict[str, str] = {}
    if harness.kind == "openai_http":
        root = resolve_base(harness, base)
        if root:
            env["GRAVEDANCER_LMSTUDIO_URL"] = f"{root}/v1/chat/completions"
    return env