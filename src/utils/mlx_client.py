"""MLX text generation client for local Apple Silicon inference."""

import importlib.util
import subprocess
import sys
from typing import Optional, List, Iterable

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

        @staticmethod
        def error(*args, **kwargs):
            return None

    st = _StreamlitFallback()


class MLXClient:
    def __init__(self, model: str = "mlx-community/Qwen3.6-27B-4bit"):
        self.model = model

    def _has_python_api(self) -> bool:
        return importlib.util.find_spec("mlx_lm") is not None

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
        chunks = list(self.generate_stream(model, prompt, system=system, temperature=temperature, top_p=top_p, max_tokens=max_tokens))
        return "".join(chunks)

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
            if self._has_python_api():
                from mlx_lm import generate as mlx_generate

                response = mlx_generate(
                    self.model,
                    prompt=prompt,
                    system=system,
                    temp=temperature,
                    max_tokens=max_tokens,
                )
                if isinstance(response, str):
                    yield response
                else:
                    yield str(response)
                return

            cmd = self._mlx_command(prompt, system=system, max_tokens=max_tokens, temperature=temperature)
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            assert proc.stdout is not None
            for line in proc.stdout:
                if line:
                    yield line
            ret = proc.wait()
            if ret != 0:
                raise RuntimeError(f"mlx_lm.generate exited with code {ret}")
        except Exception as e:
            raise Exception(f"MLX generation failed: {e}")


@st.cache_resource
def get_mlx_client(model: str = "mlx-community/Qwen3.6-27B-4bit") -> MLXClient:
    return MLXClient(model)
