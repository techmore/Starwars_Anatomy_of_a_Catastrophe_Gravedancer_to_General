"""Local storage for episodes - JSON + Markdown files."""

import json
import os
import io
import hashlib
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from uuid import uuid4

from src.utils.logging_utils import get_logger, log_timing


def _target_jedi_name(metadata: Dict[str, Any]) -> str:
    """Return the canonical target Jedi name, preferring the new field."""
    return str(metadata.get("target_jedi_name") or metadata.get("jedi_name") or "Unknown")


def _normalize_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure both legacy and canonical target Jedi keys stay in sync."""
    target = _target_jedi_name(metadata)
    metadata["jedi_name"] = target
    metadata["target_jedi_name"] = target
    return metadata


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _summarize_prompts(prompts: Optional[Dict[str, Any]]) -> Dict[str, int]:
    """Count prompt sets and covered days from a stored prompt payload."""
    scenes = prompts.get("scenes", []) if isinstance(prompts, dict) else []
    if not isinstance(scenes, list):
        scenes = []
    prompt_sets = len(scenes)
    prompt_days = len({
        p.get("day")
        for p in scenes
        if isinstance(p, dict) and isinstance(p.get("day"), int) and p.get("day") > 0
    })
    return {"prompt_sets": prompt_sets, "prompt_days": prompt_days}


class EpisodeStorage:
    _SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

    def __init__(self, base_path: str = "episodes"):
        self.base_path = Path(base_path).expanduser()
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _resolve_episode_dir(self, episode_id: str) -> Path:
        """Resolve an episode directory without allowing path traversal."""
        if not isinstance(episode_id, str) or not self._SAFE_ID_RE.fullmatch(episode_id):
            raise ValueError(f"Invalid episode id: {episode_id!r}")
        base = self.base_path.resolve()
        logical_dir = self.base_path / episode_id
        if logical_dir.resolve().parent != base:
            raise ValueError(f"Episode id escapes storage root: {episode_id!r}")
        # Keep the caller's path spelling for portable manifests/downloads;
        # the resolved-parent check above still prevents symlink traversal.
        return logical_dir

    def episode_metadata_path(self, episode_id: str) -> Path:
        """Validated path to an episode's metadata.json."""
        return self._resolve_episode_dir(episode_id) / "metadata.json"

    def _get_episode_dir(self, episode_id: str) -> Path:
        """Get/create an episode directory after validating its identifier."""
        ep_dir = self._resolve_episode_dir(episode_id)
        ep_dir.mkdir(parents=True, exist_ok=True)
        return ep_dir

    @staticmethod
    def _safe_filename(filename: str) -> str:
        """Return a basename suitable for writing inside an episode directory."""
        if not isinstance(filename, str) or not filename or Path(filename).name != filename:
            raise ValueError(f"Invalid episode filename: {filename!r}")
        if filename in {".", ".."}:
            raise ValueError(f"Invalid episode filename: {filename!r}")
        return filename

    @staticmethod
    def _safe_component(value: object, fallback: str = "item") -> str:
        """Make a user/model-provided filename component filesystem-safe."""
        cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "")).strip(".-")
        return cleaned or fallback

    @staticmethod
    def _atomic_write_text(path: Path, content: str) -> None:
        """Write text without exposing readers to a partially-written file."""
        temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            with temp_path.open("w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
        finally:
            temp_path.unlink(missing_ok=True)

    @classmethod
    def _atomic_write_json(cls, path: Path, value: Any) -> None:
        cls._atomic_write_text(path, json.dumps(value, indent=2, ensure_ascii=False))

    @staticmethod
    def _read_json(path: Path) -> Optional[Any]:
        try:
            with path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            LOGGER.warning("Unable to read JSON path=%s error=%s", path, exc)
            return None

    def _generate_episode_id(self, title: str) -> str:
        """Generate a filesystem-safe episode ID."""
        safe_title = "".join(c.lower() if c.isalnum() else "-" for c in title)
        safe_title = "-".join(filter(None, safe_title.split("-")))
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S%f")
        suffix = uuid4().hex[:8]
        return f"episode-{timestamp}-{safe_title[:50] or 'untitled'}-{suffix}"

    def save_checkpoint(
        self,
        title: str,
        metadata: Dict[str, Any],
        day_drafts: Dict[int, str],
        outline: str = "",
        scope: str = "",
    ) -> Path:
        """Atomically persist an in-progress story checkpoint.

        Checkpoints are deliberately separate from completed episodes so a
        failed run cannot appear as a finished library item. *scope* namespaces
        the checkpoint key so concurrent runs sharing a title cannot clobber
        each other's recovery data.
        """
        checkpoint_dir = self.base_path / ".checkpoints"
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_key = self._safe_component(
            _sha256_text(f"{scope}:{title}" if scope else title)[:16],
            fallback="checkpoint",
        )
        path = checkpoint_dir / f"{checkpoint_key}.json"
        payload = {
            "title": title,
            "metadata": dict(metadata or {}),
            "outline": outline or "",
            "day_drafts": {str(day): text for day, text in (day_drafts or {}).items()},
            "updated_at": datetime.now().isoformat(),
        }
        self._atomic_write_json(path, payload)
        return path

    def list_checkpoints(self) -> List[Dict[str, Any]]:
        """Return valid in-progress checkpoints, newest first."""
        checkpoint_dir = self.base_path / ".checkpoints"
        if not checkpoint_dir.is_dir():
            return []
        results: List[Dict[str, Any]] = []
        for path in checkpoint_dir.glob("*.json"):
            payload = self._read_json(path)
            if not isinstance(payload, dict) or not payload.get("title"):
                continue
            payload["path"] = str(path)
            results.append(payload)
        return sorted(results, key=lambda item: item.get("updated_at", ""), reverse=True)

    def load_checkpoint(self, checkpoint_path: str) -> Optional[Dict[str, Any]]:
        """Load a checkpoint only when it is inside the checkpoint directory."""
        checkpoint_dir = (self.base_path / ".checkpoints").resolve()
        path = Path(checkpoint_path).expanduser()
        try:
            resolved = path.resolve()
        except OSError:
            return None
        if resolved.parent != checkpoint_dir or resolved.suffix != ".json":
            return None
        payload = self._read_json(resolved)
        return payload if isinstance(payload, dict) else None

    def delete_checkpoint(self, title: str) -> bool:
        """Remove the checkpoint associated with *title*, if present."""
        checkpoint_dir = self.base_path / ".checkpoints"
        checkpoint_key = self._safe_component(_sha256_text(title)[:16], fallback="checkpoint")
        path = checkpoint_dir / f"{checkpoint_key}.json"
        try:
            path.unlink()
            return True
        except FileNotFoundError:
            return False
        except OSError as exc:
            LOGGER.warning("Unable to delete checkpoint path=%s error=%s", path, exc)
            return False

    def delete_checkpoint_file(self, checkpoint_path: str) -> bool:
        """Remove a specific checkpoint file previously returned by save_checkpoint."""
        checkpoint_dir = (self.base_path / ".checkpoints").resolve()
        path = Path(checkpoint_path).expanduser()
        try:
            resolved = path.resolve()
        except OSError:
            return False
        if resolved.parent != checkpoint_dir or resolved.suffix != ".json":
            return False
        try:
            resolved.unlink()
            return True
        except FileNotFoundError:
            return False
        except OSError as exc:
            LOGGER.warning("Unable to delete checkpoint path=%s error=%s", resolved, exc)
            return False

    def save_episode(
        self,
        title: str,
        story: str,
        metadata: Dict[str, Any],
        prompts: Optional[Dict[str, Any]] = None
    ) -> str:
        """Save episode to local storage."""
        episode_id = self._generate_episode_id(title)
        with log_timing(LOGGER, "save_episode", title=title, episode_id=episode_id):
            ep_dir = self._get_episode_dir(episode_id)
            metadata = dict(metadata or {})
            # Save metadata
            metadata["id"] = episode_id
            metadata["title"] = title
            now = datetime.now().isoformat()
            metadata["created_at"] = now
            metadata["updated_at"] = now
            _normalize_metadata(metadata)

            # Save story as markdown
            story_text = (
                f"# {title}\n\n"
                f"**Generated:** {metadata['created_at']}\n\n"
                f"**Days:** {metadata.get('num_days', 'N/A')}\n\n"
                f"**Target Jedi:** {_target_jedi_name(metadata)}\n\n"
                f"**Setting:** {metadata.get('setting', 'Unknown')}\n\n"
                "---\n\n"
                f"{story or ''}"
            )
            self._atomic_write_text(ep_dir / "story.md", story_text)

            # Save prompts if provided
            if prompts is not None:
                self._atomic_write_json(ep_dir / "prompts.json", prompts)

            # Metadata is written last as the commit marker so an interrupted
            # save never exposes a library entry without its content.
            self._atomic_write_json(ep_dir / "metadata.json", metadata)
        
        return episode_id
    
    def load_episode(self, episode_id: str) -> Optional[Dict[str, Any]]:
        """Load episode from storage."""
        LOGGER.info("load_episode start episode_id=%s", episode_id)
        try:
            ep_dir = self._resolve_episode_dir(episode_id)
        except ValueError:
            LOGGER.warning("load_episode invalid episode_id=%s", episode_id)
            return None
        if not ep_dir.is_dir():
            LOGGER.warning("load_episode missing episode_id=%s", episode_id)
            return None
        
        metadata_path = ep_dir / "metadata.json"
        story_path = ep_dir / "story.md"
        prompts_path = ep_dir / "prompts.json"
        
        if not metadata_path.exists():
            LOGGER.warning("load_episode missing metadata episode_id=%s", episode_id)
            return None
        
        metadata = self._read_json(metadata_path)
        if not isinstance(metadata, dict):
            LOGGER.warning("load_episode invalid metadata episode_id=%s", episode_id)
            return None
        _normalize_metadata(metadata)
        
        story = ""
        if story_path.exists():
            try:
                story = story_path.read_text(encoding="utf-8")
            except OSError as exc:
                LOGGER.warning("load_episode unable to read story episode_id=%s error=%s", episode_id, exc)
                return None
        
        prompts = None
        if prompts_path.exists():
            prompts = self._read_json(prompts_path)
            if prompts is not None and not isinstance(prompts, dict):
                LOGGER.warning("load_episode prompts are not an object episode_id=%s", episode_id)
                prompts = None
        
        episode = {
            "metadata": metadata,
            "story": story,
            "prompts": prompts
        }
        LOGGER.info(
            "load_episode end episode_id=%s story_chars=%s has_prompts=%s",
            episode_id,
            len(story or ""),
            bool(prompts),
        )
        return episode

    def export_episode_bundle(self, episode_id: str) -> Optional[Dict[str, Any]]:
        """Return a canonical export bundle for an episode."""
        LOGGER.info("export_episode_bundle start episode_id=%s", episode_id)
        episode = self.load_episode(episode_id)
        if not episode:
            LOGGER.warning("export_episode_bundle missing episode_id=%s", episode_id)
            return None

        metadata = dict(episode["metadata"])
        _normalize_metadata(metadata)
        story = episode["story"]
        prompts = episode.get("prompts")
        prompt_summary = _summarize_prompts(prompts)
        ep_dir = self._resolve_episode_dir(episode_id)
        files = {
            "metadata_json": str(ep_dir / "metadata.json"),
            "story_md": str(ep_dir / "story.md"),
            "prompts_json": str(ep_dir / "prompts.json"),
        }
        manifest_files = {}
        for key, file_path in files.items():
            path = Path(file_path)
            exists = path.exists()
            entry: Dict[str, Any] = {
                "path": file_path,
                "filename": path.name,
                "exists": exists,
                "size_bytes": path.stat().st_size if exists else 0,
            }
            if exists:
                entry["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            manifest_files[key] = entry

        bundle_payload = {
            "episode_id": episode_id,
            "title": metadata.get("title", "Untitled"),
            "setting": metadata.get("setting", "Unknown"),
            "created_at": metadata.get("created_at", ""),
            "num_days": metadata.get("num_days", 0),
            "metadata": metadata,
            "story": story,
            "prompts": prompts,
            "prompt_sets": prompt_summary["prompt_sets"],
            "prompt_days": prompt_summary["prompt_days"],
            "files": files,
        }

        bundle_payload["manifest"] = {
            "episode_id": episode_id,
            "generated_at": metadata.get("updated_at") or metadata.get("created_at", ""),
            "bundle_json_sha256": _sha256_text(json.dumps(bundle_payload, sort_keys=True, indent=2)),
            "files": manifest_files,
        }

        LOGGER.info(
            "export_episode_bundle end episode_id=%s story_chars=%s prompt_sets=%s prompt_days=%s",
            episode_id,
            len(story or ""),
            prompt_summary["prompt_sets"],
            prompt_summary["prompt_days"],
        )
        return bundle_payload

    def write_episode_bundle(self, episode_id: str, filename: str = "bundle.json") -> Optional[str]:
        """Write the canonical bundle to disk and return the file path."""
        LOGGER.info("write_episode_bundle start episode_id=%s filename=%s", episode_id, filename)
        bundle = self.export_episode_bundle(episode_id)
        if not bundle:
            LOGGER.warning("write_episode_bundle missing episode_id=%s", episode_id)
            return None

        ep_dir = self._resolve_episode_dir(episode_id)
        bundle_path = ep_dir / self._safe_filename(filename)
        self._atomic_write_json(bundle_path, bundle)
        LOGGER.info("write_episode_bundle end episode_id=%s path=%s", episode_id, bundle_path)
        return str(bundle_path)

    def write_episode_archive(self, episode_id: str, filename: str = "bundle.zip") -> Optional[str]:
        """Write the episode bundle and source files to a zip archive."""
        LOGGER.info("write_episode_archive start episode_id=%s filename=%s", episode_id, filename)
        archive_bytes = self.build_episode_archive_bytes(episode_id)
        if archive_bytes is None:
            LOGGER.warning("write_episode_archive missing episode_id=%s", episode_id)
            return None

        ep_dir = self._resolve_episode_dir(episode_id)
        archive_path = ep_dir / self._safe_filename(filename)
        temp_path = archive_path.with_name(f".{archive_path.name}.{uuid4().hex}.tmp")
        try:
            temp_path.write_bytes(archive_bytes)
            os.replace(temp_path, archive_path)
        finally:
            temp_path.unlink(missing_ok=True)
        LOGGER.info("write_episode_archive end episode_id=%s path=%s bytes=%s", episode_id, archive_path, len(archive_bytes))
        return str(archive_path)

    def build_episode_archive_bytes(self, episode_id: str) -> Optional[bytes]:
        """Build the episode archive as zip bytes."""
        LOGGER.info("build_episode_archive_bytes start episode_id=%s", episode_id)
        bundle = self.export_episode_bundle(episode_id)
        if not bundle:
            LOGGER.warning("build_episode_archive_bytes missing episode_id=%s", episode_id)
            return None

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("bundle.json", json.dumps(bundle, indent=2))
            zf.writestr("manifest.json", json.dumps(bundle["manifest"], indent=2))
            for key, file_path in bundle["files"].items():
                path = Path(file_path)
                if path.exists():
                    zf.write(path, arcname=path.name)
            # Keep generated keyframes and any future local video artifacts
            # with the episode archive. Do not include prior bundle/archive
            # outputs, which would make repeated exports grow recursively.
            ep_dir = self._resolve_episode_dir(episode_id)
            for media_root_name in ("images", "videos"):
                media_root = ep_dir / media_root_name
                if not media_root.is_dir():
                    continue
                for media_path in sorted(path for path in media_root.rglob("*") if path.is_file()):
                    zf.write(media_path, arcname=str(media_path.relative_to(ep_dir)))
        archive = buf.getvalue()
        LOGGER.info("build_episode_archive_bytes end episode_id=%s bytes=%s", episode_id, len(archive))
        return archive
    
    def list_episodes(self) -> List[Dict[str, Any]]:
        """List all episodes with metadata."""
        LOGGER.info("list_episodes start base_path=%s", self.base_path)
        episodes = []
        for ep_dir in sorted(self.base_path.iterdir(), key=lambda x: x.name, reverse=True):
            if ep_dir.is_dir():
                metadata_path = ep_dir / "metadata.json"
                if metadata_path.exists():
                    metadata = self._read_json(metadata_path)
                    if not isinstance(metadata, dict):
                        LOGGER.warning("list_episodes skipping invalid metadata path=%s", metadata_path)
                        continue
                    prompt_summary = {"prompt_sets": 0, "prompt_days": 0}
                    prompts_path = ep_dir / "prompts.json"
                    if prompts_path.exists():
                        prompts = self._read_json(prompts_path)
                        prompt_summary = _summarize_prompts(prompts)
                    episodes.append({
                        "id": ep_dir.name,
                        "title": metadata.get("title", "Untitled"),
                        "created_at": metadata.get("created_at", ""),
                        "num_days": metadata.get("num_days", 0),
                        "jedi_name": _target_jedi_name(metadata),
                        "target_jedi_name": _target_jedi_name(metadata),
                        "setting": metadata.get("setting", "Unknown"),
                        "prompt_sets": prompt_summary["prompt_sets"],
                        "prompt_days": prompt_summary["prompt_days"],
                    })
        LOGGER.info("list_episodes end count=%s base_path=%s", len(episodes), self.base_path)
        return episodes
    
    def delete_episode(self, episode_id: str) -> bool:
        """Delete an episode."""
        try:
            ep_dir = self._resolve_episode_dir(episode_id)
        except ValueError:
            LOGGER.warning("delete_episode invalid episode_id=%s", episode_id)
            return False
        if ep_dir.is_dir():
            shutil.rmtree(ep_dir)
            return True
        return False
    
    def update_episode(
        self,
        episode_id: str,
        story: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        prompts: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Update an existing episode.

        Any argument left as None is left untouched. When rewriting the story
        file we always read the current metadata as the header source so the
        title/setting are preserved even when only ``story`` is supplied.
        """
        try:
            ep_dir = self._resolve_episode_dir(episode_id)
        except ValueError:
            LOGGER.warning("update_episode invalid episode_id=%s", episode_id)
            return False
        if not ep_dir.is_dir():
            return False

        # Always load the current metadata so we can use it as a header source.
        metadata_path = ep_dir / "metadata.json"
        existing_metadata: Dict[str, Any] = {}
        if metadata_path.exists():
            loaded_metadata = self._read_json(metadata_path)
            if not isinstance(loaded_metadata, dict):
                return False
            existing_metadata = loaded_metadata
        else:
            return False

        # Merge new metadata into existing (does NOT wipe other fields).
        changed = False
        if metadata is not None:
            existing_metadata.update(metadata)
            incoming_target = metadata.get("target_jedi_name") or metadata.get("jedi_name")
            if incoming_target:
                existing_metadata["jedi_name"] = incoming_target
                existing_metadata["target_jedi_name"] = incoming_target
            changed = True

        # When rewriting the story, source the header from the merged metadata,
        # not from a possibly-None metadata argument.
        if story is not None:
            story_path = ep_dir / "story.md"
            title = existing_metadata.get("title", "Untitled")
            story_text = (
                f"# {title}\n\n"
                f"**Generated:** {existing_metadata.get('created_at', datetime.now().isoformat())}\n\n"
                f"**Days:** {existing_metadata.get('num_days', 'N/A')}\n\n"
                f"**Target Jedi:** {_target_jedi_name(existing_metadata)}\n\n"
                f"**Setting:** {existing_metadata.get('setting', 'Unknown')}\n\n"
                "---\n\n"
                f"{story}"
            )
            self._atomic_write_text(story_path, story_text)
            changed = True

        if prompts is not None:
            prompts_path = ep_dir / "prompts.json"
            self._atomic_write_json(prompts_path, prompts)
            changed = True

        if changed:
            _normalize_metadata(existing_metadata)
            existing_metadata["updated_at"] = datetime.now().isoformat()
            self._atomic_write_json(metadata_path, existing_metadata)

        return True

    def save_image(
        self,
        episode_id: str,
        day: int,
        shot: str,
        image_bytes: bytes,
        variant: Optional[int] = None,
    ) -> str:
        """Save a keyframe image to the episode's images/ directory.

        Returns the relative path from the episode root.
        """
        ep_dir = self._resolve_episode_dir(episode_id)
        if not ep_dir.is_dir():
            raise FileNotFoundError(f"Episode does not exist: {episode_id}")
        imgs_dir = ep_dir / "images"
        imgs_dir.mkdir(parents=True, exist_ok=True)
        if not isinstance(day, int) or day < 0:
            raise ValueError("day must be a non-negative integer")
        if variant is not None and (not isinstance(variant, int) or variant < 0):
            raise ValueError("variant must be a non-negative integer")
        safe_shot = self._safe_component(shot, fallback="keyframe")
        suffix = f"-v{variant:02d}" if variant is not None else ""
        path = imgs_dir / f"day-{day:02d}-{safe_shot}{suffix}.png"
        temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            temp_path.write_bytes(image_bytes)
            os.replace(temp_path, path)
        finally:
            temp_path.unlink(missing_ok=True)
        LOGGER.info("save_image episode_id=%s day=%s shot=%s bytes=%s path=%s", episode_id, day, shot, len(image_bytes), path)
        return str(path.relative_to(self.base_path))


def get_storage(base_path: str = "episodes") -> EpisodeStorage:
    """Create a storage instance for the requested episode directory."""
    return EpisodeStorage(base_path)
LOGGER = get_logger(__name__)
