"""Local storage for episodes - JSON + Markdown files."""

import json
import os
import io
import hashlib
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from src.utils._streamlit_fallback import st
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
    prompt_sets = len(prompts.get("scenes", [])) if isinstance(prompts, dict) else 0
    prompt_days = len({
        p.get("day")
        for p in prompts.get("scenes", [])
        if isinstance(p, dict) and isinstance(p.get("day"), int) and p.get("day") > 0
    }) if isinstance(prompts, dict) else 0
    return {"prompt_sets": prompt_sets, "prompt_days": prompt_days}


class EpisodeStorage:
    def __init__(self, base_path: str = "episodes"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
    
    def _get_episode_dir(self, episode_id: str) -> Path:
        """Get episode directory path."""
        ep_dir = self.base_path / episode_id
        ep_dir.mkdir(parents=True, exist_ok=True)
        return ep_dir
    
    def _generate_episode_id(self, title: str) -> str:
        """Generate a filesystem-safe episode ID."""
        safe_title = "".join(c.lower() if c.isalnum() else "-" for c in title)
        safe_title = "-".join(filter(None, safe_title.split("-")))
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return f"episode-{timestamp}-{safe_title[:50]}"
    
    def save_episode(
        self,
        title: str,
        story: str,
        metadata: Dict[str, Any],
        prompts: Optional[Dict[str, Any]] = None
    ) -> str:
        """Save episode to local storage."""
        episode_id = self._generate_episode_id(title)
        LOGGER.info(
            "save_episode start title=%s episode_id=%s story_chars=%s prompts=%s",
            title,
            episode_id,
            len(story or ""),
            bool(prompts),
        )
        with log_timing(LOGGER, "save_episode", title=title, episode_id=episode_id):
            ep_dir = self._get_episode_dir(episode_id)
            # Save metadata
            metadata["id"] = episode_id
            metadata["title"] = title
            metadata["created_at"] = datetime.now().isoformat()
            metadata["updated_at"] = datetime.now().isoformat()
            _normalize_metadata(metadata)

            with open(ep_dir / "metadata.json", "w") as f:
                json.dump(metadata, f, indent=2)

            # Save story as markdown
            with open(ep_dir / "story.md", "w") as f:
                f.write(f"# {title}\n\n")
                f.write(f"**Generated:** {metadata['created_at']}\n\n")
                f.write(f"**Days:** {metadata.get('num_days', 'N/A')}\n\n")
                f.write(f"**Target Jedi:** {_target_jedi_name(metadata)}\n\n")
                f.write(f"**Setting:** {metadata.get('setting', 'Unknown')}\n\n")
                f.write("---\n\n")
                f.write(story)

            # Save prompts if provided
            if prompts:
                with open(ep_dir / "prompts.json", "w") as f:
                    json.dump(prompts, f, indent=2)
        LOGGER.info("save_episode end title=%s episode_id=%s", title, episode_id)
        
        return episode_id
    
    def load_episode(self, episode_id: str) -> Optional[Dict[str, Any]]:
        """Load episode from storage."""
        LOGGER.info("load_episode start episode_id=%s", episode_id)
        ep_dir = self.base_path / episode_id
        if not ep_dir.exists():
            LOGGER.warning("load_episode missing episode_id=%s", episode_id)
            return None
        
        metadata_path = ep_dir / "metadata.json"
        story_path = ep_dir / "story.md"
        prompts_path = ep_dir / "prompts.json"
        
        if not metadata_path.exists():
            LOGGER.warning("load_episode missing metadata episode_id=%s", episode_id)
            return None
        
        with open(metadata_path, "r") as f:
            metadata = json.load(f)
        _normalize_metadata(metadata)
        
        story = ""
        if story_path.exists():
            with open(story_path, "r") as f:
                story = f.read()
        
        prompts = None
        if prompts_path.exists():
            with open(prompts_path, "r") as f:
                prompts = json.load(f)
        
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
        files = {
            "metadata_json": str(self.base_path / episode_id / "metadata.json"),
            "story_md": str(self.base_path / episode_id / "story.md"),
            "prompts_json": str(self.base_path / episode_id / "prompts.json"),
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

        ep_dir = self.base_path / episode_id
        bundle_path = ep_dir / filename
        with open(bundle_path, "w") as f:
            json.dump(bundle, f, indent=2)
        LOGGER.info("write_episode_bundle end episode_id=%s path=%s", episode_id, bundle_path)
        return str(bundle_path)

    def write_episode_archive(self, episode_id: str, filename: str = "bundle.zip") -> Optional[str]:
        """Write the episode bundle and source files to a zip archive."""
        LOGGER.info("write_episode_archive start episode_id=%s filename=%s", episode_id, filename)
        archive_bytes = self.build_episode_archive_bytes(episode_id)
        if archive_bytes is None:
            LOGGER.warning("write_episode_archive missing episode_id=%s", episode_id)
            return None

        ep_dir = self.base_path / episode_id
        archive_path = ep_dir / filename
        with open(archive_path, "wb") as f:
            f.write(archive_bytes)
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
                    with open(metadata_path, "r") as f:
                        metadata = json.load(f)
                    prompt_summary = {"prompt_sets": 0, "prompt_days": 0}
                    prompts_path = ep_dir / "prompts.json"
                    if prompts_path.exists():
                        with open(prompts_path, "r") as f:
                            prompts = json.load(f)
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
        import shutil
        ep_dir = self.base_path / episode_id
        if ep_dir.exists():
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
        ep_dir = self.base_path / episode_id
        if not ep_dir.exists():
            return False

        # Always load the current metadata so we can use it as a header source.
        metadata_path = ep_dir / "metadata.json"
        existing_metadata: Dict[str, Any] = {}
        if metadata_path.exists():
            with open(metadata_path, "r") as f:
                existing_metadata = json.load(f)

        # Merge new metadata into existing (does NOT wipe other fields).
        if metadata:
            existing_metadata.update(metadata)
            incoming_target = metadata.get("target_jedi_name") or metadata.get("jedi_name")
            if incoming_target:
                existing_metadata["jedi_name"] = incoming_target
                existing_metadata["target_jedi_name"] = incoming_target
            _normalize_metadata(existing_metadata)
            existing_metadata["updated_at"] = datetime.now().isoformat()
            with open(metadata_path, "w") as f:
                json.dump(existing_metadata, f, indent=2)

        # When rewriting the story, source the header from the merged metadata,
        # not from a possibly-None metadata argument.
        if story:
            story_path = ep_dir / "story.md"
            title = existing_metadata.get("title", "Untitled")
            with open(story_path, "w") as f:
                f.write(f"# {title}\n\n")
                f.write(f"**Generated:** {existing_metadata.get('created_at', datetime.now().isoformat())}\n\n")
                f.write(f"**Days:** {existing_metadata.get('num_days', 'N/A')}\n\n")
                f.write(f"**Target Jedi:** {_target_jedi_name(existing_metadata)}\n\n")
                f.write(f"**Setting:** {existing_metadata.get('setting', 'Unknown')}\n\n")
                f.write("---\n\n")
                f.write(story)

        if prompts is not None:
            prompts_path = ep_dir / "prompts.json"
            with open(prompts_path, "w") as f:
                json.dump(prompts, f, indent=2)

        return True

    def save_image(
        self,
        episode_id: str,
        day: int,
        shot: str,
        image_bytes: bytes,
    ) -> str:
        """Save a keyframe image to the episode's images/ directory.

        Returns the relative path from the episode root.
        """
        ep_dir = self._get_episode_dir(episode_id)
        imgs_dir = ep_dir / "images"
        imgs_dir.mkdir(parents=True, exist_ok=True)
        path = imgs_dir / f"day-{day:02d}-{shot}.png"
        path.write_bytes(image_bytes)
        LOGGER.info("save_image episode_id=%s day=%s shot=%s bytes=%s path=%s", episode_id, day, shot, len(image_bytes), path)
        return str(path.relative_to(self.base_path))


@st.cache_resource
def get_storage(base_path: str = "episodes") -> EpisodeStorage:
    """Get cached storage instance."""
    return EpisodeStorage(base_path)
LOGGER = get_logger(__name__)
