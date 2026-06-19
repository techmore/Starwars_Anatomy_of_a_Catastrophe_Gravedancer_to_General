"""Ollama client for local LLM inference."""

import requests
import json
from typing import Optional, List, Dict, Any
import streamlit as st


class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url.rstrip("/")
        self.api_generate = f"{self.base_url}/api/generate"
        self.api_chat = f"{self.base_url}/api/chat"
        self.api_tags = f"{self.base_url}/api/tags"
    
    def list_models(self) -> List[str]:
        """Get list of available models from Ollama."""
        try:
            response = requests.get(self.api_tags, timeout=5)
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
        
        try:
            response = requests.post(self.api_generate, json=payload, timeout=300)
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
            response = requests.post(self.api_generate, json=payload, stream=True, timeout=300)
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
            response = requests.get(self.api_tags, timeout=3)
            return response.status_code == 200
        except Exception:
            return False


@st.cache_resource
def get_ollama_client(base_url: str = "http://localhost:11434") -> OllamaClient:
    """Get cached Ollama client instance."""
    return OllamaClient(base_url)