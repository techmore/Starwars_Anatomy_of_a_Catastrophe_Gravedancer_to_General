"""Ollama client for local LLM inference."""

import json
import time
from typing import Optional, List, Dict, Any

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


# Retries applied on connection-level failures (not on HTTP errors from the API).
_MAX_RETRIES = 2
_RETRY_BACKOFF_SECONDS = 1.0


def _requests():
    import requests

    return requests


class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url.rstrip("/")
        self.api_generate = f"{self.base_url}/api/generate"
        self.api_chat = f"{self.base_url}/api/chat"
        self.api_tags = f"{self.base_url}/api/tags"

    def _get_with_retry(self, url: str, timeout: int = 5):
        """GET with a couple of retries on transient connection failures."""
        requests = _requests()
        last_err: Optional[Exception] = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                return requests.get(url, timeout=timeout)
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                last_err = e
                if attempt < _MAX_RETRIES:
                    time.sleep(_RETRY_BACKOFF_SECONDS)
        assert last_err is not None
        raise last_err

    def _post_with_retry(self, url: str, json_payload: Dict[str, Any], timeout: int = 300, stream: bool = False):
        """POST with a couple of retries on transient connection failures."""
        requests = _requests()
        last_err: Optional[Exception] = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                return requests.post(url, json=json_payload, timeout=timeout, stream=stream)
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                last_err = e
                if attempt < _MAX_RETRIES:
                    time.sleep(_RETRY_BACKOFF_SECONDS)
        assert last_err is not None
        raise last_err

    def list_models(self) -> List[str]:
        """Get list of available models from Ollama."""
        try:
            response = self._get_with_retry(self.api_tags, timeout=5)
            response.raise_for_status()
            data = response.json()
            return [model["name"] for model in data.get("models", [])]
        except Exception as e:
            st.error(f"Failed to fetch models from Ollama: {e}")
            return []

    def generate(
        self,
        model: str,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.7,
        top_p: float = 0.9,
        max_tokens: int = 4096,
        stream: bool = False
    ) -> str:
        """Generate text using Ollama."""
        payload = {
            "model": model,
            "prompt": prompt,
            "temperature": temperature,
            "top_p": top_p,
            "num_predict": max_tokens,
            "stream": stream
        }
        if system:
            payload["system"] = system

        requests = _requests()
        try:
            response = self._post_with_retry(self.api_generate, payload, timeout=300)
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")
        except requests.exceptions.Timeout:
            raise Exception("Request timed out. The model may be taking too long to respond.")
        except Exception as e:
            raise Exception(f"Ollama generation failed: {e}")

    def generate_stream(
        self,
        model: str,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.7,
        top_p: float = 0.9,
        max_tokens: int = 4096
    ):
        """Generate text with streaming."""
        payload = {
            "model": model,
            "prompt": prompt,
            "temperature": temperature,
            "top_p": top_p,
            "num_predict": max_tokens,
            "stream": True
        }
        if system:
            payload["system"] = system

        try:
            response = self._post_with_retry(self.api_generate, payload, timeout=300, stream=True)
            response.raise_for_status()

            for line in response.iter_lines():
                if line:
                    data = json.loads(line)
                    yield data.get("response", "")
                    if data.get("done", False):
                        break
        except Exception as e:
            raise Exception(f"Ollama streaming failed: {e}")

    def check_connection(self) -> bool:
        """Check if Ollama is running and accessible."""
        try:
            response = self._get_with_retry(self.api_tags, timeout=3)
            return response.status_code == 200
        except Exception:
            return False


@st.cache_resource
def get_ollama_client(base_url: str = "http://localhost:11434") -> OllamaClient:
    """Get cached Ollama client instance."""
    return OllamaClient(base_url)
