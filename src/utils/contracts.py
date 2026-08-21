"""Small protocol contracts shared by workflows and UI composition."""

from collections.abc import Callable, Iterable
from typing import Any, Protocol

ProgressCallback = Callable[[str, str, str], None]


class TextGenerationBackend(Protocol):
    """Backend required by story and prompt workflows."""

    def generate_stream(
        self,
        model: str,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.7,
        top_p: float = 0.9,
        max_tokens: int = 4096,
    ) -> Iterable[str]:
        ...

    def generate(
        self,
        model: str,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.7,
        top_p: float = 0.9,
        max_tokens: int = 4096,
        stream: bool = False,
    ) -> str:
        ...


class EpisodeRepository(Protocol):
    """Persistence contract consumed by UI workflows."""

    def list_episodes(self) -> list[dict[str, Any]]:
        ...

    def load_episode(self, episode_id: str) -> dict[str, Any] | None:
        ...

    def save_episode(
        self,
        title: str,
        story: str,
        metadata: dict[str, Any],
        prompts: dict[str, Any] | None = None,
    ) -> str:
        ...


class ImageGenerationBackend(Protocol):
    """Minimal Draw Things contract used by the UI."""

    def check_connection(self) -> bool:
        ...


class StoryWorkflow(Protocol):
    """Marker contract for the story workflow façade."""


class PromptWorkflow(Protocol):
    """Marker contract for the prompt workflow façade."""
