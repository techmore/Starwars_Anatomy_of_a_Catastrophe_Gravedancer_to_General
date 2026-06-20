"""Shared application context for the UI shell."""

from dataclasses import dataclass


@dataclass
class AppContext:
    """Bundle the services and current settings used across tabs."""

    mlx: object
    dt_client: object
    mlx_model: str
    temperature: float
    storage: object
    story_gen: object
    prompt_gen: object
