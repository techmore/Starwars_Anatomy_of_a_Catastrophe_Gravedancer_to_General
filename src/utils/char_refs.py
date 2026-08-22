"""Character reference sheet generation for Flux.2 Klein multi-ref conditioning.

Phase 1 of the image pipeline: generate canonical character portraits from the
episode metadata, saved to ``<episode>/refs/``. These become the reference
images passed to Draw Things (multi-ref) for every subsequent chapter/day
render, keeping identities consistent without LoRA training.

Usage from the pipeline:
    refs = generate_character_refs(storage, dt_client, episode_id, metadata)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.utils.drawthings_client import DrawThingsClient
from src.utils.logging_utils import get_logger
from src.utils.storage import EpisodeStorage

LOGGER = get_logger(__name__)

REFS_DIR = "refs"


def _character_sheet_specs(metadata: dict[str, Any]) -> list[dict[str, str]]:
    """Build character-sheet specs from episode metadata."""
    specs: list[dict[str, str]] = []
    jedi_name = metadata.get("jedi_name") or metadata.get("target_jedi_name")
    if jedi_name:
        specs.append({
            "shot": f"ref-{_slug(str(jedi_name))}",
            "label": f"Jedi: {jedi_name}",
            "prompt": (
                "Character reference portrait, painterly Star Wars sci-fi realism. "
                f"{metadata.get('jedi_rank', 'Jedi')} named {jedi_name}, "
                f"a {metadata.get('jedi_species', 'human')}. "
                f"Personality visible in bearing: {metadata.get('jedi_personality', 'calm and disciplined')}. "
                "Single figure, waist-up, neutral background, soft key light, "
                "full face clearly visible, NO text, no letters."
            ),
        })
    return specs


def _location_sheet_spec(metadata: dict[str, Any]) -> dict[str, str]:
    setting = str(metadata.get("setting", "")).split(".")[0]
    return {
        "shot": "ref-primary-location",
        "label": f"Location: {setting}",
        "prompt": (
            "Establishing location reference, painterly Star Wars sci-fi realism. "
            f"{setting}. No characters present. Wide establishing composition, "
            "volumetric light, dramatic atmosphere, NO text, no letters."
        ),
    }


def _slug(value: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "ref"


def generate_character_refs(
    storage: EpisodeStorage,
    dt_client: DrawThingsClient,
    episode_id: str,
    metadata: dict[str, Any],
    steps: int = 25,
    cfg: float = 2.5,
) -> list[dict[str, Any]]:
    """Generate canonical reference sheets into ``<episode>/refs/``.

    One sheet per named character + one primary location. Non-fatal per
    sheet; returns a manifest.
    """
    try:
        ep_dir = storage._resolve_episode_dir(episode_id)
        refs_dir = ep_dir / REFS_DIR
        refs_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        LOGGER.warning("refs skip: cannot resolve episode dir error=%s", exc)
        return []

    specs = _character_sheet_specs(metadata) + [_location_sheet_spec(metadata)]
    results: list[dict[str, Any]] = []
    for spec in specs:
        LOGGER.info("ref gen begin shot=%s", spec["shot"])
        try:
            png = dt_client.generate_image(
                prompt=spec["prompt"], width=1024, height=1024,
                steps=steps, cfg=cfg)
            path = refs_dir / f"{spec['shot']}.png"
            path.write_bytes(png)
            results.append({
                "shot": spec["shot"],
                "label": spec["label"],
                "path": str(path),
            })
            LOGGER.info("ref gen done shot=%s path=%s", spec["shot"], path)
        except Exception as exc:
            LOGGER.warning("ref gen failed shot=%s error=%s", spec["shot"], exc)
            results.append({"shot": spec["shot"], "error": str(exc)})
    return results


def list_reference_images(episode_id_path: Path) -> list[Path]:
    """Return existing ref images for multi-reference conditioning."""
    refs = Path(episode_id_path) / REFS_DIR
    if not refs.is_dir():
        return []
    return sorted(refs.glob("*.png"))
