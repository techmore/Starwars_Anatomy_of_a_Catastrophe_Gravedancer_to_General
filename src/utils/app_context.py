"""Shared application context for the UI shell."""

from dataclasses import dataclass

from src.utils.contracts import (
    EpisodeRepository,
    ImageGenerationBackend,
    PromptWorkflow,
    StoryWorkflow,
    TextGenerationBackend,
)


@dataclass
class AppContext:
    """Bundle the services and current settings used across tabs."""

    mlx: TextGenerationBackend
    dt_client: ImageGenerationBackend
    mlx_model: str
    temperature: float
    storage: EpisodeRepository
    story_gen: StoryWorkflow
    prompt_gen: PromptWorkflow
