"""MLX text generation client for local Apple Silicon inference."""

import importlib.util
import gc
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from src.utils.logging_utils import get_logger
from src.utils.models import DEFAULT_MODEL, list_local_mlx_models, normalize_model_name


LOGGER = get_logger(__name__)


BONSAI_1BIT_MODEL = "prism-ml/Bonsai-27B-mlx-1bit"
BONSAI_RUNTIME_DEFAULT = Path.home() / ".local" / "share" / "gravedancer" / "bonsai-runtime" / "bin" / "python"
BONSAI_RUNNER = Path(__file__).with_name("bonsai_runner.py")
BONSAI_REPETITION_PENALTY = 1.08
BONSAI_REPETITION_CONTEXT = 256
BONSAI_FREQUENCY_PENALTY = 0.04
LMSTUDIO_PREFIX = "lmstudio:"
LMSTUDIO_URL = "http://127.0.0.1:1234/v1/chat/completions"
OPENCODE_PREFIX = "opencode:"
OPENCODE_DEFAULT_MODEL = "opencode-go/deepseekv4-free"


def lmstudio_api_url() -> str:
    """Return the configured OpenAI-compatible LM Studio chat endpoint."""
    return os.environ.get("GRAVEDANCER_LMSTUDIO_URL", LMSTUDIO_URL).strip() or LMSTUDIO_URL


def lmstudio_base_url() -> str:
    """Return the server root used for the lightweight health check."""
    return lmstudio_api_url().rsplit("/v1/", 1)[0]


def _lmstudio_max_tokens() -> int:
    """Return a bounded LM Studio output ceiling for long-form generation."""
    raw_value = os.environ.get("GRAVEDANCER_LMSTUDIO_MAX_TOKENS", "8192")
    try:
        return max(256, min(int(raw_value), 32768))
    except ValueError:
        return 8192


LMSTUDIO_MAX_TOKENS = _lmstudio_max_tokens()


def _configure_local_model_mode() -> bool:
    """Keep model loading offline unless the user explicitly opts into downloads.

    The app is designed to run after local MLX models have been prepared. This
    prevents a generation click from silently fetching or updating model files;
    set ``GRAVEDANCER_ALLOW_MODEL_DOWNLOADS=1`` before starting the app to
    intentionally allow Hugging Face access.
    """
    if os.environ.get("GRAVEDANCER_ALLOW_MODEL_DOWNLOADS") == "1":
        return False
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    return True


LOCAL_MODEL_MODE = _configure_local_model_mode()

_OPTIQ_REGISTERED = False


def _ensure_optiq_model_types() -> None:
    """Register OptiQ-patched model types (e.g. gemma4_unified) just-in-time.

    The OptiQ package patches mlx_lm to recognize Gemma 4's unified text
    tower, and the import must happen before any mlx_lm load call. Importing
    it at module scope cost ~3s of startup for every entrypoint because it
    eagerly pulls in mlx_lm and transformers, so registration now happens on
    the native-load path only. Optional: non-Gemma models load fine without it.
    """
    global _OPTIQ_REGISTERED
    if _OPTIQ_REGISTERED:
        return
    try:
        import optiq  # noqa: F401 — side effect: registers model type
    except ImportError:
        pass
    _OPTIQ_REGISTERED = True

try:
    from rich.console import Console as RichConsole
    from rich.live import Live
    from rich.spinner import Spinner
    from rich.text import Text
    RICH_LIVE_AVAILABLE = True
except ImportError:
    RichConsole = Live = Spinner = Text = None
    RICH_LIVE_AVAILABLE = False


_THINK_OPEN = "<think>"
_THINK_CLOSE = "</think>"
_THINK_OPEN_LEN = len(_THINK_OPEN)
_THINK_CLOSE_LEN = len(_THINK_CLOSE)

# Plain-text reasoning prefixes that Qwen3.5 emits (no <think> tags).
# These appear at the START of the response and continue until the model
# either produces real output or runs out of tokens.
_PLAIN_THINK_RE = re.compile(
    r"(?is)^\s*(?:Thinking\s*(?:in\s+Qwen)?|Thinking\s+Process|Analysis|Planning|"
    r"Let\s+me\s+think|I\s+need\s+to\s+think|I\s+should\s+think)"
    r"\s*:?\s*",
)


def _strip_think_blocks(text: str) -> str:
    """Remove chain-of-thought markup from streamed output.

    Handles three reasoning formats:
    1. ``<think>``...``</think>`` tags (standard thinking blocks)
    2. Partial ``<think>`` with no closing tag (streaming truncation)
    3. Plain-text "Thinking Process:" / "Thinking in Qwen:" prefixes
       that Qwen3.5 emits instead of ``<think>`` tags

    Works correctly on all chunks because ``response.text`` is
    *cumulative* -- each call sees the complete output so far.
    """
    # First: strip plain-text "Thinking Process:" prefix (Qwen3.5 format).
    # Only strip from the start — if it appears mid-text, the reasoning
    # already ended and real content was produced before it.
    text = _PLAIN_THINK_RE.sub("", text, count=1)

    # Second: strip <think> tags (standard format)
    lower = text.lower()
    parts: list[str] = []
    pos = 0
    while True:
        open_pos = lower.find(_THINK_OPEN, pos)
        if open_pos < 0:
            parts.append(text[pos:])
            break
        parts.append(text[pos:open_pos])
        close_pos = lower.find(_THINK_CLOSE, open_pos + _THINK_OPEN_LEN)
        if close_pos < 0:
            # Think block not yet closed — drop the rest
            break
        pos = close_pos + _THINK_CLOSE_LEN
    return "".join(parts)


def _apply_chat_template(tokenizer, prompt: str, system: Optional[str] = None) -> str:
    """Format a prompt using the model's chat template.

    This is critical for chat models (Qwen, Llama, etc.) — without it,
    the model receives raw text and may not recognize it as a user
    message, triggering uncontrolled reasoning or continuation behavior.

    Falls back to the raw prompt if the tokenizer has no chat template.
    """
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    try:
        # Gemma 4's template supports this flag and otherwise begins its
        # response in a reasoning channel.  Disabling it keeps generation
        # focused on the user-visible answer; older model templates simply
        # reject the extra keyword and use the compatibility fallback below.
        return tokenizer.apply_chat_template(
            messages,
            add_generation_prompt=True,
            enable_thinking=False,
        )
    except TypeError:
        try:
            return tokenizer.apply_chat_template(
                messages,
                add_generation_prompt=True,
            )
        except Exception:
            return prompt
    except Exception:
        return prompt


def _redact_command_arguments(command: List[str]) -> str:
    """Render a subprocess command without logging user/story prompt text."""
    sensitive_flags = {"--prompt", "--system"}
    rendered = []
    redact_next = False
    for argument in command:
        if redact_next:
            rendered.append("<redacted>")
            redact_next = False
        else:
            rendered.append(argument)
            if argument in sensitive_flags:
                redact_next = True
    return " ".join(rendered)


def _bonsai_runtime_python() -> Path:
    """Return the separately-installed Prism MLX interpreter, if configured."""
    return Path(os.environ.get("GRAVEDANCER_BONSAI_PYTHON", BONSAI_RUNTIME_DEFAULT)).expanduser()


class MLXClient:
    def __init__(self, model: str = DEFAULT_MODEL):
        self.model = model
        # Track the model whose objects are currently resident in the MLX
        # cache.  Explicit cleanup is important on Apple Silicon where weights
        # share unified memory.
        self._active_model: Optional[str] = None
        self._loaded_model: Optional[tuple] = None

    def _has_python_api(self) -> bool:
        return importlib.util.find_spec("mlx_lm") is not None

    @staticmethod
    def _is_lmstudio_model(model: str) -> bool:
        return str(model).startswith(LMSTUDIO_PREFIX)

    @staticmethod
    def _is_opencode_model(model: str) -> bool:
        return str(model).startswith(OPENCODE_PREFIX)

    @staticmethod
    def _opencode_model_id(model: str) -> str:
        return str(model)[len(OPENCODE_PREFIX):] or OPENCODE_DEFAULT_MODEL

    def _generate_opencode_stream(self, model, prompt, system, max_tokens):
        """Run OpenCode as an external provider, preserving app streaming."""
        opencode = os.environ.get("GRAVEDANCER_OPENCODE_BIN", "opencode")
        message = f"{system}\n\n{prompt}" if system else prompt
        command = [opencode, "run", "--format", "json", "--model", self._opencode_model_id(model), message]
        LOGGER.info("using OpenCode model=%s cwd=%s", self._opencode_model_id(model), Path.cwd())
        try:
            proc = subprocess.Popen(command, cwd=str(Path.cwd()), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        except OSError as exc:
            raise RuntimeError(f"Could not start OpenCode: {exc}") from exc
        assert proc.stdout is not None
        # Drain stderr concurrently so a chatty child can never fill the pipe
        # and deadlock the stdout loop.
        stderr_chunks: List[str] = []
        stderr_thread = threading.Thread(
            target=lambda: stderr_chunks.append(proc.stderr.read() if proc.stderr else ""),
            daemon=True,
        )
        stderr_thread.start()
        try:
            for line in proc.stdout:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                text = event.get("text")
                if text is None and isinstance(event.get("part"), dict):
                    text = event["part"].get("text")
                if text:
                    yield _strip_think_blocks(str(text))
            if proc.wait() != 0:
                raise RuntimeError("".join(stderr_chunks)[-2000:] or "OpenCode run failed")
        finally:
            self._reap_stream_process(proc)
            stderr_thread.join(timeout=2)

    @staticmethod
    def _lmstudio_model_id(model: str) -> str:
        return str(model)[len(LMSTUDIO_PREFIX):]

    @staticmethod
    def _lmstudio_prompt(prompt: str) -> str:
        """Disable Ornith/Qwen-style hidden reasoning when supported."""
        text = str(prompt or "")
        return text if "/no_think" in text.lower() else f"{text}\n/no_think"

    def check_lmstudio(self, model: str | None = None, timeout: float = 10.0) -> dict:
        """Check LM Studio before a run and report whether the model is loaded."""
        if model is not None and not self._is_lmstudio_model(model):
            return {"available": True, "model_loaded": True, "models": [], "error": ""}
        requested = self._lmstudio_model_id(model or self.model)
        url = f"{lmstudio_base_url()}/v1/models"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, method="GET"), timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            models = [str(item.get("id", "")) for item in payload.get("data", []) if isinstance(item, dict)]
            loaded = not requested or requested in models
            return {"available": True, "model_loaded": loaded, "models": models, "error": "" if loaded else f"Model not loaded: {requested}"}
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            return {"available": False, "model_loaded": False, "models": [], "error": str(exc)}

    def _generate_lmstudio(self, model: str, prompt: str, system: Optional[str],
                           temperature: float, top_p: float, max_tokens: int) -> str:
        """Call an OpenAI-compatible local LM Studio server."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": self._lmstudio_prompt(prompt)})
        payload = json.dumps({
            "model": self._lmstudio_model_id(model),
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": min(max_tokens, LMSTUDIO_MAX_TOKENS),
            "stream": False,
            "reasoning_effort": "none",
            # Qwen 3.8 exposes this LM Studio chat-template option. The
            # production prompts already contain explicit planning steps;
            # hidden reasoning here only consumes the output budget.
            "chat_template_kwargs": {"enable_thinking": False},
        }).encode("utf-8")
        request = urllib.request.Request(
            lmstudio_api_url(), data=payload,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=max(180, max_tokens // 2)) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"LM Studio request failed: {exc}") from exc
        try:
            choice = data["choices"][0]
            content = choice["message"].get("content") or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"LM Studio returned an unexpected response: {data}") from exc
        return _strip_think_blocks(content).strip()

    def _generate_lmstudio_stream(
        self, model: str, prompt: str, system: Optional[str],
        temperature: float, top_p: float, max_tokens: int,
    ) -> Iterable[str]:
        """Yield OpenAI-compatible LM Studio SSE deltas as they arrive."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": self._lmstudio_prompt(prompt)})
        payload = json.dumps({
            "model": self._lmstudio_model_id(model),
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": min(max_tokens, LMSTUDIO_MAX_TOKENS),
            "stream": True,
            "reasoning_effort": "none",
            "chat_template_kwargs": {"enable_thinking": False},
        }).encode("utf-8")
        request = urllib.request.Request(
            lmstudio_api_url(), data=payload,
            headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=max(180, max_tokens // 2)) as response:
                raw_output = ""
                emitted_output = ""
                for raw_line in response:
                    line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith("data:"):
                        line = line[5:].strip()
                    if line == "[DONE]":
                        return
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    choices = event.get("choices") or []
                    if not choices or not isinstance(choices[0], dict):
                        continue
                    choice = choices[0]
                    delta = choice.get("delta") or {}
                    text = delta.get("content")
                    if text:
                        raw_output += str(text)
                        # Hold an incomplete tag at the end of a streamed
                        # response until the next delta arrives.
                        lower_tail = raw_output.lower()
                        partial_tags = (
                            ["<think"[:index] for index in range(1, len("<think") + 1)]
                            + ["</think"[:index] for index in range(1, len("</think") + 1)]
                        )
                        if any(lower_tail.endswith(tag) for tag in partial_tags):
                            continue
                        cleaned_output = _strip_think_blocks(raw_output)
                        if cleaned_output.startswith(emitted_output):
                            visible_delta = cleaned_output[len(emitted_output):]
                        else:
                            # A malformed backend response should not duplicate
                            # already-emitted text, but preserve new content.
                            visible_delta = cleaned_output
                        emitted_output = cleaned_output
                        if visible_delta:
                            yield visible_delta
                    elif choice.get("finish_reason"):
                        return
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"LM Studio streaming request failed: {exc}") from exc

    def _load_model(self, model_name: str):
        # Instance-level single-slot cache. A class-level lru_cache here made
        # every MLXClient share one entry keyed by (self, model), so a second
        # client evicted the first and forced full weight reloads from disk.
        if self._loaded_model is not None:
            return self._loaded_model
        _ensure_optiq_model_types()
        if self._is_mlx_vlm_model(model_name):
            from mlx_vlm import load
            from mlx_vlm.utils import load_config

            model, processor = load(normalize_model_name(model_name))
            config = load_config(normalize_model_name(model_name))
            loaded = ("mlx_vlm", model, processor, config)
        else:
            from mlx_lm import load

            model, tokenizer = load(normalize_model_name(model_name))
            loaded = ("mlx_lm", model, tokenizer)
        self._loaded_model = loaded
        return loaded

    @staticmethod
    def _is_mlx_vlm_model(model_name: str) -> bool:
        """Qwen3.8 MLX checkpoints use mlx-vlm even for text-only prompts."""
        name = str(model_name).lower()
        return "qwen3.8" in name or "qwen3_8" in name

    def _ensure_model_loaded(self, model_name: str):
        """Load one model at a time and explicitly release the prior model."""
        normalized = normalize_model_name(model_name)
        if self._active_model is not None and self._active_model != normalized:
            self.release_loaded_model()
        loaded = self._load_model(normalized)
        self._active_model = normalized
        return loaded

    def release_loaded_model(self) -> None:
        """Drop this client's loaded MLX model before switching workloads.

        MLX model weights occupy unified memory alongside Draw Things. Keeping
        only one cached model per client and clearing it on an explicit UI
        switch prevents stale model weights from accumulating in a 32 GB run.
        """
        self._loaded_model = None
        self._active_model = None
        # Drop Python references and ask MLX/Metal to return reclaimable
        # buffers.  These calls are optional so the client remains testable
        # without MLX installed.
        gc.collect()
        try:
            import mlx.core as mx
            mx.clear_cache()
        except (ImportError, AttributeError):
            pass
        LOGGER.info("released cached MLX model model=%s", self.model)

    def _mlx_command(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        model: Optional[str] = None,
    ) -> List[str]:
        cmd = [
            sys.executable,
            "-m",
            "mlx_lm.generate",
            "--model",
            normalize_model_name(model or self.model),
            "--prompt",
            prompt,
            "--max-tokens",
            str(max_tokens),
            "--temperature",
            str(temperature),
        ]
        if system:
            cmd.extend(["--system", system])
        return cmd

    def list_models(self) -> List[str]:
        return [self.model]

    def check_connection(self) -> bool:
        return self._has_python_api()

    def is_model_available_locally(self, model: Optional[str] = None) -> bool:
        """Check a local path or Hugging Face cache without loading the model."""
        normalized = normalize_model_name(model or self.model)
        if Path(normalized).expanduser().is_dir():
            return True
        return normalized in {repo_id for _, repo_id in list_local_mlx_models()}

    def is_model_supported_by_runtime(self, model: Optional[str] = None) -> bool:
        """Return whether the active MLX runtime can execute a model's weights.

        Bonsai 27B's published MLX package uses 1-bit quantization.  Mainline
        MLX currently supports 2-bit and higher weights, so merely finding the
        model in the Hugging Face cache is not sufficient to call it ready.
        """
        if normalize_model_name(model or self.model) != BONSAI_1BIT_MODEL:
            return True
        runtime = _bonsai_runtime_python()
        if not runtime.is_file():
            return False
        try:
            check = subprocess.run(
                [str(runtime), "-c", "import mlx.core as mx; mx.quantize(mx.zeros((1, 128)), group_size=128, bits=1)"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return check.returncode == 0

    @staticmethod
    def _reap_stream_process(proc: subprocess.Popen) -> None:
        """Terminate a streaming child left behind by an abandoned generator."""
        if proc.poll() is not None:
            return
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                LOGGER.warning("Stream child pid=%s ignored SIGKILL", proc.pid)
        except OSError as exc:
            LOGGER.warning("Unable to reap stream child pid=%s error=%s", proc.pid, exc)

    def _bonsai_command(self) -> List[str]:
        runtime = _bonsai_runtime_python()
        if not runtime.is_file():
            raise RuntimeError(
                "Bonsai requires the isolated Prism MLX runtime. Run the documented "
                "Bonsai setup or set GRAVEDANCER_BONSAI_PYTHON to its Python executable."
            )
        return [str(runtime), "-u", str(BONSAI_RUNNER)]

    def _generate_bonsai_stream(
        self, model: str, prompt: str, system: Optional[str], temperature: float,
        top_p: float, max_tokens: int,
    ) -> Iterable[str]:
        command = self._bonsai_command()
        env = os.environ.copy()
        env.setdefault("HF_HUB_OFFLINE", "1")
        env.setdefault("TRANSFORMERS_OFFLINE", "1")
        request = {
            "model": model, "prompt": prompt, "system": system,
            "temperature": temperature, "top_p": top_p, "max_tokens": max_tokens,
            "repetition_penalty": BONSAI_REPETITION_PENALTY,
            "repetition_context": BONSAI_REPETITION_CONTEXT,
            "frequency_penalty": BONSAI_FREQUENCY_PENALTY,
        }
        LOGGER.info("using isolated Bonsai runtime model=%s max_tokens=%s", model, max_tokens)
        process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, env=env,
        )
        assert process.stdin is not None
        process.stdin.write(json.dumps(request) + "\n")
        process.stdin.close()
        assert process.stdout is not None
        # Drain stderr concurrently so a chatty runtime can never fill the
        # pipe and deadlock the stdout loop.
        stderr_chunks: List[str] = []
        stderr_thread = threading.Thread(
            target=lambda: stderr_chunks.append(process.stderr.read() if process.stderr else ""),
            daemon=True,
        )
        stderr_thread.start()
        error = ""
        try:
            for line in process.stdout:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "delta":
                    cleaned = _strip_think_blocks(event.get("text", ""))
                    if cleaned:
                        yield cleaned
                elif event.get("type") == "error":
                    error = event.get("message", "Bonsai runtime failed")
            if process.wait() != 0:
                raise RuntimeError(error or "".join(stderr_chunks)[-1000:] or "Bonsai runtime failed")
        finally:
            self._reap_stream_process(process)
            stderr_thread.join(timeout=2)

    def generate(
        self,
        model: str,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.7,
        top_p: float = 0.9,
        max_tokens: int = 4096,
        stream: bool = False,
    ) -> str:
        start = time.perf_counter()
        LOGGER.info(
            "generate requested model=%s max_tokens=%s temperature=%.2f top_p=%.2f prompt_chars=%s system_chars=%s stream=%s",
            model,
            max_tokens,
            temperature,
            top_p,
            len(prompt or ""),
            len(system or ""),
            stream,
        )
        heartbeat_stop = threading.Event()
        live = None
        if RICH_LIVE_AVAILABLE and sys.stderr.isatty():
            live = Live(
                Spinner("dots", text=f"Generating with {Path(str(model)).name}"),
                refresh_per_second=8,
                transient=False,
                console=RichConsole(file=sys.stderr),
            )
            live.start()

        def heartbeat() -> None:
            started = time.perf_counter()
            while not heartbeat_stop.wait(10.0):
                elapsed = time.perf_counter() - started
                status = f"Generating with {Path(str(model)).name} — {elapsed:.0f}s elapsed"
                if live:
                    live.update(Spinner("dots", text=status))
                else:
                    print(f"\r  [model] {status}", end="", file=sys.stderr, flush=True)

        heartbeat_thread = threading.Thread(target=heartbeat, daemon=True)
        heartbeat_thread.start()
        try:
            chunks = list(self.generate_stream(model, prompt, system=system, temperature=temperature, top_p=top_p, max_tokens=max_tokens))
        finally:
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=0.2)
            if live:
                live.update(Text(f"✓ Generation finished: {Path(str(model)).name}", style="green"))
                live.stop()
            else:
                print("\r  [model] generation finished.              ", file=sys.stderr, flush=True)
        text = "".join(chunks)
        LOGGER.info("generate completed model=%s elapsed=%.3fs output_chars=%s", model, time.perf_counter() - start, len(text))
        return text

    def generate_stream(
        self,
        model: str,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.7,
        top_p: float = 0.9,
        max_tokens: int = 4096,
    ) -> Iterable[str]:
        try:
            normalized_model = normalize_model_name(model)
            if self._is_opencode_model(model):
                yield from self._generate_opencode_stream(model, prompt, system, max_tokens)
                return
            if self._is_lmstudio_model(model):
                health = self.check_lmstudio(model)
                if not health["available"]:
                    raise RuntimeError(
                        "LM Studio is not running. Start its local server at http://127.0.0.1:1234 and retry."
                    )
                if not health["model_loaded"]:
                    raise RuntimeError(health["error"] or "The selected LM Studio model is not loaded.")
                start = time.perf_counter()
                LOGGER.info("using LM Studio model=%s max_tokens=%s", self._lmstudio_model_id(model), max_tokens)
                output_chars = 0
                for chunk in self._generate_lmstudio_stream(model, prompt, system, temperature, top_p, max_tokens):
                    output_chars += len(chunk)
                    yield chunk
                LOGGER.info("LM Studio completed model=%s elapsed=%.3fs output_chars=%s",
                            self._lmstudio_model_id(model), time.perf_counter() - start, output_chars)
                return
            if normalized_model == BONSAI_1BIT_MODEL:
                yield from self._generate_bonsai_stream(
                    normalized_model, prompt, system, temperature, top_p, max_tokens
                )
                return
            if self._has_python_api():
                LOGGER.info(
                    "using mlx_lm python API model=%s normalized=%s prompt_chars=%s system_chars=%s max_tokens=%s temperature=%.2f top_p=%.2f",
                    model,
                    normalized_model,
                    len(prompt or ""),
                    len(system or ""),
                    max_tokens,
                    temperature,
                    top_p,
                )
                from mlx_lm import stream_generate
                from mlx_lm.sample_utils import make_sampler

                loaded = self._ensure_model_loaded(normalized_model)
                if loaded[0] == "mlx_vlm":
                    from mlx_vlm import generate as vlm_generate
                    from mlx_vlm.prompt_utils import apply_chat_template

                    _, vlm_model, processor, config = loaded
                    vlm_prompt = prompt
                    if system:
                        vlm_prompt = f"{system}\n\n{prompt}"
                    formatted_prompt = apply_chat_template(
                        processor,
                        config,
                        vlm_prompt,
                        num_images=0,
                        enable_thinking=False,
                    )
                    output = vlm_generate(
                        vlm_model, processor, formatted_prompt,
                        image=None, max_tokens=max_tokens,
                        temperature=temperature, top_p=top_p, verbose=False,
                    )
                    output_text = getattr(output, "text", output)
                    cleaned = _strip_think_blocks(str(output_text)).strip()
                    if cleaned:
                        yield cleaned
                    return
                _, loaded_model, tokenizer = loaded
                # Apply chat template so the model sees a proper user
                # message instead of raw text.  This prevents Qwen3.5
                # from entering uncontrolled reasoning mode.
                formatted_prompt = _apply_chat_template(tokenizer, prompt, system)
                sampler = make_sampler(temp=temperature, top_p=top_p)
                emitted_text = ""
                start = time.perf_counter()
                chunk_count = 0
                for response in stream_generate(
                    loaded_model,
                    tokenizer,
                    formatted_prompt,
                    max_tokens=max_tokens,
                    sampler=sampler,
                ):
                    chunk_count += 1
                    cleaned = _strip_think_blocks(response.text)
                    if not cleaned:
                        continue
                    if cleaned.startswith(emitted_text):
                        delta = cleaned[len(emitted_text):]
                    else:
                        delta = cleaned
                    emitted_text = cleaned
                    if delta:
                        yield delta
                LOGGER.info(
                    "mlx_lm python API completed model=%s normalized=%s elapsed=%.3fs chunks=%s output_chars=%s output_preview=%s",
                    model,
                    normalized_model,
                    time.perf_counter() - start,
                    chunk_count,
                    len(emitted_text),
                    repr(emitted_text[:200]),
                )
                return

            cmd = self._mlx_command(
                prompt,
                system=system,
                max_tokens=max_tokens,
                temperature=temperature,
                model=normalized_model,
            )
            LOGGER.info(
                "using mlx_lm subprocess model=%s normalized=%s prompt_chars=%s system_chars=%s max_tokens=%s temperature=%.2f top_p=%.2f cmd=%s",
                model,
                normalized_model,
                len(prompt or ""),
                len(system or ""),
                max_tokens,
                temperature,
                top_p,
                _redact_command_arguments(cmd),
            )
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            assert proc.stdout is not None
            emitted_text = ""
            start = time.perf_counter()
            line_count = 0
            for line in proc.stdout:
                if line:
                    line_count += 1
                    cleaned = _strip_think_blocks(line)
                    if not cleaned:
                        continue
                    if cleaned.startswith(emitted_text):
                        delta = cleaned[len(emitted_text):]
                    else:
                        delta = cleaned
                    emitted_text = cleaned
                    if delta:
                        yield delta
            ret = proc.wait()
            LOGGER.info(
                "mlx_lm subprocess completed model=%s normalized=%s elapsed=%.3fs lines=%s code=%s",
                model,
                normalized_model,
                time.perf_counter() - start,
                line_count,
                ret,
            )
            if ret != 0:
                LOGGER.error("mlx_lm subprocess exited non-zero model=%s code=%s", model, ret)
                raise RuntimeError(f"mlx_lm.generate exited with code {ret}")
        except Exception as e:
            LOGGER.exception("MLX generation failed model=%s", model)
            raise RuntimeError(f"MLX generation failed: {e}") from e


def get_mlx_client(model: str = DEFAULT_MODEL) -> MLXClient:
    """Create an MLX client for a model identifier.

    UI layers may cache this factory result if desired; the integration layer
    itself remains independent of Streamlit and other presentation frameworks.
    """
    return MLXClient(normalize_model_name(model))
