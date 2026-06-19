"""Local storage for episodes - JSON + Markdown files."""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import streamlit as st


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
        ep_dir = self._get_episode_dir(episode_id)
        
        # Save metadata
        metadata["id"] = episode_id
        metadata["title"] = title
        metadata["created_at"] = datetime.now().isoformat()
        metadata["updated_at"] = datetime.now().isoformat()
        
        with open(ep_dir / "metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)
        
        # Save story as markdown
        with open(ep_dir / "story.md", "w") as f:
            f.write(f"# {title}\n\n")
            f.write(f"**Generated:** {metadata['created_at']}\n\n")
            f.write(f"**Days:** {metadata.get('num_days', 'N/A')}\n\n")
            f.write(f"**Jedi Target:** {metadata.get('jedi_name', 'Unknown')}\n\n")
            f.write(f"**Setting:** {metadata.get('setting', 'Unknown')}\n\n")
            f.write("---\n\n")
            f.write(story)
        
        # Save prompts if provided
        if prompts:
            with open(ep_dir / "prompts.json", "w") as f:
                json.dump(prompts, f, indent=2)
        
        return episode_id
    
    def load_episode(self, episode_id: str) -> Optional[Dict[str, Any]]:
        """Load episode from storage."""
        ep_dir = self.base_path / episode_id
        if not ep_dir.exists():
            return None
        
        metadata_path = ep_dir / "metadata.json"
        story_path = ep_dir / "story.md"
        prompts_path = ep_dir / "prompts.json"
        
        if not metadata_path.exists():
            return None
        
        with open(metadata_path, "r") as f:
            metadata = json.load(f)
        
        story = ""
        if story_path.exists():
            with open(story_path, "r") as f:
                story = f.read()
        
        prompts = None
        if prompts_path.exists():
            with open(prompts_path, "r") as f:
                prompts = json.load(f)
        
        return {
            "metadata": metadata,
            "story": story,
            "prompts": prompts
        }
    
    def list_episodes(self) -> List[Dict[str, Any]]:
        """List all episodes with metadata."""
        episodes = []
        for ep_dir in sorted(self.base_path.iterdir(), key=lambda x: x.name, reverse=True):
            if ep_dir.is_dir():
                metadata_path = ep_dir / "metadata.json"
                if metadata_path.exists():
                    with open(metadata_path, "r") as f:
                        metadata = json.load(f)
                    episodes.append({
                        "id": ep_dir.name,
                        "title": metadata.get("title", "Untitled"),
                        "created_at": metadata.get("created_at", ""),
                        "num_days": metadata.get("num_days", 0),
                        "jedi_name": metadata.get("jedi_name", "Unknown"),
                        "setting": metadata.get("setting", "Unknown")
                    })
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
        """Update an existing episode."""
        ep_dir = self.base_path / episode_id
        if not ep_dir.exists():
            return False
        
        if metadata:
            metadata_path = ep_dir / "metadata.json"
            with open(metadata_path, "r") as f:
                existing_metadata = json.load(f)
            existing_metadata.update(metadata)
            existing_metadata["updated_at"] = datetime.now().isoformat()
            with open(metadata_path, "w") as f:
                json.dump(existing_metadata, f, indent=2)
        
        if story:
            story_path = ep_dir / "story.md"
            title = metadata.get("title") if metadata else "Untitled"
            with open(story_path, "w") as f:
                f.write(f"# {title}\n\n")
                meta = metadata or {}
                f.write(f"**Generated:** {meta.get('created_at', datetime.now().isoformat())}\n\n")
                f.write(f"**Days:** {meta.get('num_days', 'N/A')}\n\n")
                f.write(f"**Jedi Target:** {meta.get('jedi_name', 'Unknown')}\n\n")
                f.write(f"**Setting:** {meta.get('setting', 'Unknown')}\n\n")
                f.write("---\n\n")
                f.write(story)
        
        if prompts is not None:
            prompts_path = ep_dir / "prompts.json"
            with open(prompts_path, "w") as f:
                json.dump(prompts, f, indent=2)
        
        return True


@st.cache_resource
def get_storage(base_path: str = "episodes") -> EpisodeStorage:
    """Get cached storage instance."""
    return EpisodeStorage(base_path)