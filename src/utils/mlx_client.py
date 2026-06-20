"""MLX text generation client for local Apple Silicon inference."""

import importlib.util
import logging
import re
import subprocess
import sys
import time
from functools import lru_cache
from typing import Optional, List, Iterable

from src.utils._streamlit_fallback import st
from src.utils.logging_utils import get_logger
from src.utils.models import normalize_model_name


LOGGER = get_logger(__name__)

# Register the gemma4_unified model type before any mlx_lm load calls.
# The OptiQ package patches mlx_lm to recognize Gemma 4's unified text tower.
# Import is optional — non-Gemma models work without it.
try:
    import optiq  # noqa: F401 — side effect: registers model type
except ImportError:
    pass


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
        return tokenizer.apply_chat_template(
            messages, add_generation_prompt=True,
        )
    except Exception:
        return prompt


class MLXClient:
    def __init__(self, model: str = "mlx-community/gemma-4-12B-it-OptiQ-4bit"):
        self.model = model

    def _has_python_api(self) -> bool:
        return importlib.util.find_spec("mlx_lm") is not None

    @lru_cache(maxsize=4)
    def _load_model(self, model_name: str):
        from mlx_lm import load

        return load(normalize_model_name(model_name))

    def _mlx_command(self, prompt: str, system: Optional[str] = None, max_tokens: int = 4096, temperature: float = 0.7) -> List[str]:
        cmd = [
            sys.executable,
            "-m",
            "mlx_lm.generate",
            "--model",
            self.model,
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
        chunks = list(self.generate_stream(model, prompt, system=system, temperature=temperature, top_p=top_p, max_tokens=max_tokens))
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

                loaded_model, tokenizer = self._load_model(normalized_model)
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

            cmd = self._mlx_command(prompt, system=system, max_tokens=max_tokens, temperature=temperature)
            cmd[3] = normalized_model
            LOGGER.info(
                "using mlx_lm subprocess model=%s normalized=%s prompt_chars=%s system_chars=%s max_tokens=%s temperature=%.2f top_p=%.2f cmd=%s",
                model,
                normalized_model,
                len(prompt or ""),
                len(system or ""),
                max_tokens,
                temperature,
                top_p,
                " ".join(cmd[:8]) + (" ..." if len(cmd) > 8 else ""),
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
            raise Exception(f"MLX generation failed: {e}")


@st.cache_resource
def get_mlx_client(model: str = "mlx-community/gemma-4-12B-it-OptiQ-4bit") -> MLXClient:
    return MLXClient(normalize_model_name(model))
