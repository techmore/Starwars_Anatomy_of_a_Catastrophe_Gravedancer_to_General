#!/usr/bin/env python3
"""Textual TUI for the Gravedancer → General creative pipeline.

Cross-platform (macOS + Linux) launcher that makes model + harness selection
explicit and can drive multiple pipeline runs side by side — local (any
harness) and/or remote (an SSH target, e.g. an Ubuntu box):

    * pick an inference harness (rapid-mlx / LM Studio / Ollama / remote
      OpenAI endpoint / native MLX), filtered to what this platform supports
    * browse the models that harness actually serves (GET /v1/models for HTTP,
      local MLX cache for native mode)
    * optionally point at a remote host, deploy the project over rsync/SSH
      (creating a venv if missing), and run the pipeline there
    * every run streams live into its own shared log; select a run to inspect
      it; stop the selected run locally (SIGTERM) or remotely (ssh pkill)

Run with:  python tui.py
"""

from __future__ import annotations

import json
import os
import platform
import random
import re
import signal
import subprocess
import sys
import time
import uuid
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    OptionList,
    RichLog,
    Select,
    Static,
)
from textual.widgets.option_list import Option

from src.utils import harness as harness_mod
from src.utils import remoter as remoter_mod
from src.utils.creative_tables import generate_creative_seed
from src.utils.remoter import RemoteTarget
from src.utils.settings import SETTINGS

PROJECT_ROOT = Path(__file__).resolve().parent

STATE_PATH = Path.home() / ".gravedancer" / "tui-state.json"


def _load_tui_state() -> Dict[str, Any]:
    """Load persisted TUI selections (harness/model/seed/url), tolerating absence."""
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_tui_state(state: Dict[str, Any]) -> None:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        pass


def find_model_disk_path(model_id: str) -> Optional[Path]:
    """Locate a locally downloaded MLX checkpoint directory for *model_id*."""
    for root in (PROJECT_ROOT / ".models", Path.home() / ".models"):
        candidate = root / model_id
        if candidate.is_dir() and (candidate / "config.json").is_file():
            return candidate
    return None


def server_serves(base: str, model_id: str, timeout: float = 2.0) -> bool:
    """True when the OpenAI-compatible server at *base* lists *model_id*."""
    try:
        return model_id in harness_mod.list_served_models_at(base)
    except Exception:
        return False


def port_of(base: str, default: int = 1234) -> int:
    from urllib.parse import urlparse

    try:
        port = urlparse(base).port
        return port or default
    except ValueError:
        return default


_HTML_CSS = """
body { font-family: Georgia, 'Times New Roman', serif; background: #14171c;
       color: #d8d4c8; max-width: 46rem; margin: 0 auto; padding: 2.5rem 1.5rem 5rem; }
h1 { font-size: 1.9rem; color: #e8ddc0; letter-spacing: .02em; margin-bottom: .2rem; }
.meta { color: #8a94a6; font-size: .85rem; font-family: ui-monospace, monospace;
        margin-bottom: 2rem; border-bottom: 1px solid #2a2f3a; padding-bottom: 1rem; }
h2 { color: #c9a86a; font-size: 1.25rem; margin-top: 2.8rem; border-bottom:
     1px dashed #3a4050; padding-bottom: .3rem; }
h3 { color: #9fb4cc; font-size: 1.02rem; margin-top: 1.8rem; }
.wc { float: right; color: #5c6678; font-size: .75rem; font-family: ui-monospace, monospace; }
p { line-height: 1.75; margin: .9rem 0; text-align: justify; }
.total { margin-top: 3rem; padding-top: 1rem; border-top: 1px solid #2a2f3a;
         color: #8a94a6; font-family: ui-monospace, monospace; font-size: .85rem; }
"""


def write_episode_html(base_path: Path, episode_id: str) -> Optional[Path]:
    """Render an episode as a styled HTML reading view.

    Returns the written file path, or None when the episode has no story yet.
    The file lands inside the episode directory as preview.html.
    """
    import html as _html

    ep_dir = base_path / episode_id
    story_path = ep_dir / "story.md"
    if not story_path.is_file():
        return None
    story = story_path.read_text(encoding="utf-8")
    meta_path = ep_dir / "metadata.json"
    try:
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        metadata = {}

    title = _html.escape(str(metadata.get("title", episode_id)))
    jedi = _html.escape(str(metadata.get("target_jedi_name")
                            or metadata.get("jedi_name") or "?"))
    model = _html.escape(str(metadata.get("model_story") or metadata.get("model") or "?"))
    tone = ", ".join(metadata.get("tone_focus", []) or [])
    meta_line = (f"Days: {metadata.get('num_days', '?')} · Jedi: {jedi} · "
                 f"Tone: {_html.escape(tone) or '?'} · Model: {model}")

    body_parts: List[str] = []
    total_words = 0
    blocks = re.split(r"(?=^## DAY \d+:)", story, flags=re.MULTILINE)
    day_re = re.compile(r"^## DAY (\d+):\s*(.+)$", re.MULTILINE)
    for block in blocks:
        m = day_re.match(block)
        if not m:
            continue
        day_words = len(block.split())
        total_words += day_words
        body_parts.append(
            f"<h2>Day {m.group(1)} — {_html.escape(m.group(2).strip())}"
            f"<span class='wc'>{day_words:,} words</span></h2>"
        )
        prose = day_re.sub("", block, count=1)
        prose = re.sub(r"^### Chapter \d+:.*$", "", prose, flags=re.MULTILINE)
        for para in [p.strip() for p in prose.split("\n\n") if p.strip()]:
            body_parts.append(f"<p>{_html.escape(para).replace(chr(10), '<br>')}</p>")
    if not body_parts:
        return None

    html_doc = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{title}</title><style>{_HTML_CSS}</style></head><body>"
        f"<h1>{title}</h1><div class='meta'>{meta_line}</div>"
        + "\n".join(body_parts)
        + f"<div class='total'>Total: {total_words:,} words across "
          f"{metadata.get('num_days', '?')} days · Gravedancer → General</div>"
        "</body></html>"
    )
    out = ep_dir / "preview.html"
    out.write_text(html_doc, encoding="utf-8")
    return out

_EPISODE_ID_RE = re.compile(r"Episode saved:\s*(\S+)")

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07|\x1b\][^\x07]*\x1b\\")
_METER_RE = re.compile(r"\|\s*~[\d,]+ tokens|\belapsed\b")

_STATUS_SYMBOLS = {"running": "▶", "finished": "✓", "stopped": "■", "error": "✗"}


@dataclass
class RunRecord:
    """A single pipeline run (local subprocess or SSH-attached remote run)."""

    run_id: str
    label: str
    local: bool
    seed: int
    started: float
    popen: Optional[subprocess.Popen] = None
    target: Optional[RemoteTarget] = None
    marker: str = ""
    status: str = "running"
    code: Optional[int] = None
    ended: Optional[float] = None
    lines: List[str] = field(default_factory=list)
    episode_id: Optional[str] = None
    progress: "RunProgress" = field(default_factory=lambda: RunProgress())
    activity: str = ""
    error_tail: str = ""
    server_proc: Optional[subprocess.Popen] = None
    server_base: str = ""
    server_model: str = ""


class RunLine(Message):
    def __init__(self, run_id: str, text: str) -> None:
        super().__init__()
        self.run_id = run_id
        self.text = text


class RunDone(Message):
    def __init__(self, run_id: str, code: int) -> None:
        super().__init__()
        self.run_id = run_id
        self.code = code


def _progress_bar(pct: float, width: int = 10) -> str:
    filled = max(0, min(width, int(pct / 100 * width)))
    return "█" * filled + "░" * (width - filled)


class RunProgress:
    """Derive live completion %, stage tree, and token counts from pipeline output.

    Anchor weights: outline 10%, story 70%, banner 2%, chapter prompts 16%,
    save 2%. Story fraction derives from "[section] Day X: expanding section
    Y/Z" lines; per-section token counts come from the streaming meter lines
    ("[day-X-section-Y] ... | ~N tokens |").
    """

    _RE_DAYS = re.compile(r"^\s*Days:\s+(\d+)", re.MULTILINE)
    _RE_PHASE = re.compile(r"PHASE (\d):")
    _RE_OUTLINE_DONE = re.compile(r"Outline (?:generated|reused)")
    _RE_SECTION = re.compile(r"\[section\] Day (\d+): expanding section (\d+)/(\d+)")
    _RE_SECTION_TOKENS = re.compile(
        r"\[day-(\d+)-section-(\d+)\].*?~([\d,]+) tokens"
    )
    _RE_OUTLINE_TOKENS = re.compile(r"\[outline\].*?~([\d,]+) tokens")
    _RE_DAY_DONE = re.compile(r"\[day\] Day (\d+) complete \(([\d,]+) chars\)")
    _RE_CHECKPOINT_REUSE = re.compile(r"\[checkpoint\] Reusing checkpoint for Day (\d+)")
    _RE_STORY_DONE = re.compile(r"Story generated \(")
    _RE_CHAPTERS = re.compile(r"Extracted (\d+) chapters")
    _RE_BANNER_DONE = re.compile(r"Banner prompt generated")
    _RE_CHAPTER_PROMPT = re.compile(r"Chapter (\d+)/(\d+)")
    _RE_SAVED = re.compile(r"Episode saved:")

    def __init__(self) -> None:
        self.num_days = 0
        self.pct = 0.0
        self.stage = "starting"
        self.chapters_total = 0
        # day -> {"sections": n, "done": bool, "tokens": {sec: tokens}, "chars": int}
        self.days: Dict[int, Dict[str, Any]] = {}
        self.outline_tokens = 0
        self.current_day = 0
        self.current_section = 0
        self.chapter_prompts_done = 0

    def _day(self, day: int) -> Dict[str, Any]:
        return self.days.setdefault(
            day, {"sections": 0, "done": False, "tokens": {}, "chars": 0})

    @property
    def tokens_total(self) -> int:
        total = self.outline_tokens
        for info in self.days.values():
            total += sum(info["tokens"].values())
        return total

    def words_estimate(self) -> int:
        """Estimated finished words: exact-ish for completed days (chars/5),
        token-derived (~tokens*0.8) for in-flight sections."""
        words = 0
        for day, info in self.days.items():
            if info["done"] and info["chars"]:
                words += info["chars"] // 5
            else:
                words += sum(info["tokens"].values()) * 4 // 5
        return words

    def update(self, line: str) -> bool:
        """Consume one output line; returns True when the display changed."""
        before = (round(self.pct, 1), self.stage, self.tokens_total,
                  self.current_day, self.current_section, self.chapter_prompts_done)
        m = self._RE_DAYS.search(line)
        if m:
            self.num_days = int(m.group(1))
        if self._RE_PHASE.search(line):
            phase = int(self._RE_PHASE.search(line).group(1))
            anchors = {1: ("outline", 2.0), 2: ("story", None), 3: ("chapters", 80.5),
                       4: ("banner", 81.0), 5: ("chapter prompts", 82.0), 6: ("saving", 98.0)}
            stage, floor_pct = anchors.get(phase, (self.stage, None))
            self.stage = stage
            if floor_pct is not None:
                self.pct = max(self.pct, floor_pct)
        m = self._RE_OUTLINE_TOKENS.search(line)
        if m:
            self.outline_tokens = max(self.outline_tokens, int(m.group(1).replace(",", "")))
        if self._RE_OUTLINE_DONE.search(line):
            self.stage = "outline done"
            self.pct = max(self.pct, 10.0)
        m = self._RE_SECTION.search(line)
        if m and self.num_days:
            day, sec, sec_count = int(m.group(1)), int(m.group(2)), int(m.group(3))
            info = self._day(day)
            info["sections"] = sec_count
            self.current_day, self.current_section = day, sec
            frac = ((day - 1) + (sec - 1) / max(sec_count, 1)) / self.num_days
            self.stage = f"story · day {day}/{self.num_days} · section {sec}/{sec_count}"
            self.pct = max(self.pct, 10.0 + 70.0 * min(frac, 1.0))
        m = self._RE_SECTION_TOKENS.search(line)
        if m:
            tokens = int(m.group(3).replace(",", ""))
            self._day(int(m.group(1)))["tokens"][int(m.group(2))] = max(
                tokens, self._day(int(m.group(1)))["tokens"].get(int(m.group(2)), 0))
        m = self._RE_DAY_DONE.search(line) or self._RE_CHECKPOINT_REUSE.search(line)
        if m and self.num_days:
            day = int(m.group(1))
            info = self._day(day)
            info["done"] = True
            if m.lastindex and m.lastindex >= 2:
                info["chars"] = max(info["chars"], int(m.group(2).replace(",", "")))
            for sec in range(1, info["sections"] + 1):
                info["tokens"].setdefault(sec, info["tokens"].get(sec, 0))
            self.stage = f"story · day {day}/{self.num_days} complete"
            self.pct = max(self.pct, 10.0 + 70.0 * min(day / self.num_days, 1.0))
        if self._RE_STORY_DONE.search(line):
            self.stage = "story done"
            self.pct = max(self.pct, 80.0)
        m = self._RE_CHAPTERS.search(line)
        if m:
            self.chapters_total = int(m.group(1))
        if self._RE_BANNER_DONE.search(line):
            self.stage = "banner done"
            self.pct = max(self.pct, 83.0)
        m = self._RE_CHAPTER_PROMPT.search(line)
        if m and int(m.group(2)) > 0:
            i, n = int(m.group(1)), int(m.group(2))
            self.chapter_prompts_done = max(self.chapter_prompts_done, i)
            self.stage = f"chapter prompts {i}/{n}"
            self.pct = max(self.pct, 83.0 + 15.0 * (i / n))
        if self._RE_SAVED.search(line):
            self.stage = "saved"
            self.pct = 100.0
        return (round(self.pct, 1), self.stage, self.tokens_total,
                self.current_day, self.current_section, self.chapter_prompts_done) != before

    def label_suffix(self) -> str:
        return f"[{_progress_bar(self.pct)}] {self.pct:3.0f}% · {self.stage}"

    def render_tree(self, elapsed_seconds: float) -> str:
        """Multi-line stage tree for the progress panel."""
        hh, rem = divmod(max(0, int(elapsed_seconds)), 3600)
        mm, ss = divmod(rem, 60)
        lines = [
            f"[bold]{_progress_bar(self.pct)}[/] {self.pct:3.0f}%  · "
            f"runtime {hh}:{mm:02d}:{ss:02d}  · ~{self.words_estimate():,} words",
        ]

        def mark(done: bool, active: bool) -> str:
            if done:
                return "[green]✓[/]"
            if active:
                return "[cyan]▶[/]"
            return "◦"

        outline_active = self.stage.startswith("outline") and self.pct < 10
        lines.append(f"{mark(self.pct >= 10, outline_active)} outline"
                     + (f" · ~{self.outline_tokens:,} tok" if self.outline_tokens else ""))

        if self.num_days:
            chips = []
            for day in range(1, self.num_days + 1):
                info = self.days.get(day)
                done = bool(info and info["done"])
                active = (day == self.current_day and not done
                          and self.stage.startswith("story"))
                chip = f"{mark(done, active)} D{day}"
                if done and info["chars"]:
                    chip += f" ~{info['chars'] // 5:,}w"
                elif info and info["tokens"]:
                    tok = sum(info["tokens"].values())
                    if tok:
                        chip += f" {tok / 1000:.1f}k tok"
                elif active:
                    chip += " …"
                chips.append(chip)
                if active and self.current_section:
                    chips[-1] += f" ch{self.current_section}/{info['sections'] or '?'}"
            story_done = self.pct >= 80
            lines.append(f"{mark(story_done, self.stage.startswith('story'))} story "
                         f"[{_progress_bar(min(100, max(0, (self.pct - 10) / 0.7)), 8)}]")
            lines.append("  " + "  ".join(chips))

        if self.chapters_total:
            done = self.chapter_prompts_done >= self.chapters_total
            active = 0 < self.chapter_prompts_done < self.chapters_total or (
                self.stage.startswith("chapter prompts") and not done)
            lines.append(f"{mark(done, active)} visual prompts "
                         f"{self.chapter_prompts_done}/{self.chapters_total}")
        saved = self.pct >= 100
        lines.append(f"{mark(saved, self.stage.startswith('saving') and not saved)} save episode")
        return "\n".join(lines)


class EpisodeViewerScreen(Screen):
    """Browse and read saved episodes without leaving the TUI."""

    TITLE = "Episode Library"

    CSS = """
    #viewer-main { height: 1fr; }
    #ep-list-pane { width: 46; min-width: 36; max-width: 60; border-right: heavy #335577; padding: 0 1; }
    #ep-list { height: 1fr; border: round $surface; }
    #ep-read-pane { width: 1fr; padding: 0 1; }
    #ep-meta { height: auto; margin-bottom: 1; color: $accent; }
    #ep-body { height: 1fr; border: round $surface; }
    """

    BINDINGS = [
        Binding("escape", "close_viewer", "Back"),
        Binding("r", "refresh_episodes", "Refresh"),
        Binding("1", "view_story", "Story"),
        Binding("2", "view_prompts", "Prompts"),
        Binding("3", "view_info", "Info"),
        Binding("b", "open_in_browser", "Browser"),
    ]

    VIEWS = ("story", "prompts", "info")

    def __init__(self, highlight_episode: Optional[str] = None) -> None:
        super().__init__()
        self.highlight_episode = highlight_episode
        self.view_mode = "story"
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._current_id: Optional[str] = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="viewer-main"):
            with Vertical(id="ep-list-pane"):
                yield Static("Episodes (newest first)", classes="section")
                yield OptionList(id="ep-list")
            with VerticalScroll(id="ep-read-pane"):
                yield Static("Select an episode…", id="ep-meta", markup=True)
                yield RichLog(id="ep-body", markup=False, wrap=True, auto_scroll=False)

    def on_mount(self) -> None:
        self._refresh_list()

    def action_refresh_episodes(self) -> None:
        self._refresh_list()

    def _refresh_list(self) -> None:
        self.query_one("#ep-list", OptionList).clear_options()
        self.query_one("#ep-meta", Static).update("[yellow]Loading library…[/]")
        self._load_worker()

    @work(thread=True, exclusive=True)
    def _load_worker(self) -> None:
        from src.utils.storage import EpisodeStorage

        try:
            episodes = EpisodeStorage(str(SETTINGS.storage_path)).list_episodes()
        except Exception as exc:
            self.app.call_from_thread(
                self.query_one("#ep-meta", Static).update,
                f"[red]Could not list episodes: {exc}[/]",
            )
            return
        self.app.call_from_thread(self._apply_episodes, episodes)

    def _apply_episodes(self, episodes: List[dict]) -> None:
        listing = self.query_one("#ep-list", OptionList)
        listing.clear_options()
        if not episodes:
            self.query_one("#ep-meta", Static).update(
                "[yellow]No episodes yet — run the pipeline first.[/]"
            )
            return
        for ep in episodes:
            label = f"{ep.get('created_at', '')[:10]} · {ep.get('title', 'Untitled')} ({ep.get('num_days', '?')}d)"
            listing.add_option(Option(label, id=str(ep["id"])))
        target_index = 0
        if self.highlight_episode:
            for idx, ep in enumerate(episodes):
                if str(ep["id"]) == self.highlight_episode:
                    target_index = idx
                    break
        listing.highlighted = target_index

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option_list.id != "ep-list" or event.option.id is None:
            return
        self._open_episode(str(event.option.id))

    @work(thread=True, exclusive=True)
    def _open_episode(self, episode_id: str) -> None:
        import json

        base = SETTINGS.storage_path
        meta_path = base / episode_id / "metadata.json"
        story_path = base / episode_id / "story.md"
        prompts_path = base / episode_id / "prompts.json"
        try:
            metadata = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}
            story = story_path.read_text(encoding="utf-8") if story_path.is_file() else "(no story.md found)"
            prompts = json.loads(prompts_path.read_text(encoding="utf-8")) if prompts_path.is_file() else {}
        except Exception as exc:
            story = f"(could not read episode: {exc})"
            metadata, prompts = {}, {}
        payload = {
            "metadata": metadata,
            "story": story,
            "prompts": prompts,
            "meta_line": self._build_meta_line(episode_id, metadata, story),
        }
        self.app.call_from_thread(self._apply_payload, episode_id, payload)

    @staticmethod
    def _build_meta_line(episode_id: str, metadata: dict, story: str) -> str:
        words = len(story.split())
        model = metadata.get("model_story") or metadata.get("model") or "?"
        jedi = metadata.get("target_jedi_name") or metadata.get("jedi_name") or "?"
        return (
            f"[bold]{metadata.get('title', episode_id)}[/] · Days: {metadata.get('num_days', '?')}"
            f" · Jedi: {jedi} · Words: {words:,} · Model: {model}"
            f" · [1 story · 2 prompts · 3 info]"
        )

    def _apply_payload(self, episode_id: str, payload: Dict[str, Any]) -> None:
        self._cache[episode_id] = payload
        if self._current_id != episode_id:
            self._current_id = episode_id
            self.view_mode = "story"
        self.query_one("#ep-meta", Static).update(payload["meta_line"])
        self._render_view()

    def _render_view(self) -> None:
        payload = self._cache.get(self._current_id or "")
        body = self.query_one("#ep-body", RichLog)
        body.clear()
        if not payload:
            body.write("Select an episode…")
            return
        if self.view_mode == "story":
            body.write(payload["story"])
        elif self.view_mode == "prompts":
            body.write(self._format_prompts(payload["prompts"]))
        else:
            body.write(self._format_info(payload))

    @staticmethod
    def _format_prompts(prompts: Dict[str, Any]) -> str:
        if not prompts:
            return "(no prompts.json — generate visual prompts for this episode first)"
        lines: List[str] = []
        banner = prompts.get("banner") or {}
        if banner.get("prompt"):
            lines.append("════ BANNER PROMPT ════\n")
            lines.append(str(banner["prompt"]).strip())
            neg = str(banner.get("negative_prompt", "")).strip()
            if neg:
                lines.append(f"\n\nNegative: {neg}")
        chapters = prompts.get("chapters") or []
        for ch in chapters:
            title = ch.get("chapter_title", f"Chapter {ch.get('chapter', '?')}")
            lines.append(
                f"\n\n════ Day {ch.get('day', '?')} · Chapter {ch.get('chapter', '?')}: {title} "
                f"[{ch.get('aspect_ratio', '16:9')}] ════\n"
            )
            for key, label in (("wide", "Establishing"), ("medium", "Action"), ("closeup", "Close-up")):
                shot = str(ch.get(key, "")).strip()
                if shot:
                    lines.append(f"\n• {label}: {shot}")
        if not lines:
            return "(prompts.json is empty)"
        return "\n".join(lines)

    @staticmethod
    def _format_info(payload: Dict[str, Any]) -> str:
        import json as _json

        metadata = payload["metadata"]
        story = payload["story"]
        day_pattern = re.compile(r"^## DAY (\d+):\s*(.+)$", re.MULTILINE)
        chapter_pattern = re.compile(r"^### Chapter (\d+):", re.MULTILINE)
        lines = ["════ EPISODE INFO ╔══", ""]
        for key in ("title", "created_at", "num_days", "seed_value", "pipeline",
                    "jedi_name", "jedi_species", "jedi_rank",
                    "jedi_lightsaber_color", "story_arc", "story_conflict",
                    "story_resolution", "transformation_arc"):
            if metadata.get(key):
                lines.append(f"{key:>22}: {metadata[key]}")
        tone = metadata.get("tone_focus")
        if tone:
            lines.append(f"{'tone_focus':>22}: {', '.join(tone)}")
        days = day_pattern.findall(story)
        if days:
            lines.append("")
            lines.append("── structure ──")
            sections = chapter_pattern.findall(story)
            per_day = max(1, round(len(sections) / max(len(days), 1))) if sections else 0
            words_total = 0
            blocks = re.split(r"(?=^## DAY \d+:)", story, flags=re.MULTILINE)
            for block in blocks:
                m = day_pattern.match(block)
                if not m:
                    continue
                wc = len(block.split())
                words_total += wc
                lines.append(f"  {m.group(1)}: {m.group(2).strip()}  ({wc:,} words)")
            lines.append(f"  total: {words_total:,} words · {len(days)} days · ~{per_day} chapters/day")
        lines.append("")
        lines.append("── raw metadata ──")
        lines.append(_json.dumps(metadata, indent=2, ensure_ascii=False, default=str))
        return "\n".join(lines)

    def _show_episode(self, meta_line: str, story: str) -> None:
        self.query_one("#ep-meta", Static).update(meta_line)
        body = self.query_one("#ep-body", RichLog)
        body.clear()
        body.write(story)

    def action_view_story(self) -> None:
        self._switch_view("story")

    def action_view_prompts(self) -> None:
        self._switch_view("prompts")

    def action_view_info(self) -> None:
        self._switch_view("info")

    def _switch_view(self, mode: str) -> None:
        self.view_mode = mode
        self._render_view()

    def action_open_in_browser(self) -> None:

        if not self._current_id:
            return
        path = write_episode_html(SETTINGS.storage_path, self._current_id)
        if path is None:
            self.app.call_from_thread(
                self.query_one("#ep-meta", Static).update,
                "[yellow]No story.md to preview.[/]",
            )
            return
        webbrowser.open(path.as_uri())

    def action_close_viewer(self) -> None:
        self.app.pop_screen()


class QuitConfirmScreen(ModalScreen[str]):
    """Shown when quitting with active runs: keep them, kill them, or cancel."""

    CSS = """
    QuitConfirmScreen {
        align: center middle;
        background: $background 60%;
    }
    #quit-box {
        width: 64;
        height: auto;
        padding: 1 2;
        border: heavy $accent;
        background: $surface;
    }
    #quit-title { text-style: bold; margin-bottom: 1; }
    #quit-buttons { height: auto; margin-top: 1; }
    #quit-buttons Button { margin-right: 1; }
    """

    def __init__(self, active_count: int) -> None:
        super().__init__()
        self.active_count = active_count

    def compose(self) -> ComposeResult:
        with Vertical(id="quit-box"):
            yield Static(
                f"[bold]{self.active_count} run(s) still active.[/]\n"
                "Keep them running in the background, kill them, or stay.",
                id="quit-title",
            )
            with Horizontal(id="quit-buttons"):
                yield Button("Stay", id="q-stay", variant="default")
                yield Button("Quit, keep runs", id="q-keep", variant="warning")
                yield Button("Kill all & quit", id="q-kill", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        choice = {"q-stay": "cancel", "q-keep": "keep", "q-kill": "kill"}.get(
            event.button.id, "cancel"
        )
        self.dismiss(choice)


class GravedancerTUI(App):
    """Drive local and remote creative pipelines from one terminal."""

    TITLE = "Gravedancer → General"
    SUB_TITLE = f"structured creative pipeline · {platform.system()} {platform.machine()}"

    CSS = """
    #main {
        height: 1fr;
    }
    #controls {
        width: 52;
        min-width: 44;
        max-width: 68;
        padding: 0 1;
        border-right: heavy #335577;
    }
    #output {
        width: 1fr;
        height: 1fr;
        padding: 0 1;
    }
    .section {
        text-style: bold;
        color: $accent;
        margin-top: 1;
    }
    #harness, #seed {
        margin-bottom: 1;
    }
    #models {
        height: 1fr;
        min-height: 5;
        border: round $surface;
    }
    #remote-box {
        margin-top: 1;
    }
    .remote-header {
        height: auto;
    }
    .remote-header Static {
        width: auto;
    }
    .remote-header Button {
        width: auto;
        min-width: 8;
        margin-left: 1;
        height: 1;
        border: none;
        background: transparent;
    }
    #custom-url {
        margin-top: 1;
        display: none;
    }
    #button-row {
        height: auto;
        margin-top: 1;
    }
    #status {
        margin-top: 1;
        height: auto;
        max-height: 6;
        color: $text;
        border-top: dashed $surface-lighten-1;
        padding-top: 1;
    }
    #progress-panel {
        height: auto;
        max-height: 8;
        border: round $surface;
        padding: 0 1;
    }
    #progress-panel.hidden {
        display: none;
    }
    #runs {
        height: 8;
        border: round $surface;
    }
    #log {
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh_models", "Refresh models"),
        Binding("ctrl+enter", "run_local", "Run local"),
        Binding("x", "stop_run", "Stop selected"),
        Binding("v", "open_viewer", "Episodes"),
        Binding("o", "open_last_episode", "Last episode"),
        Binding("n", "random_seed", "Random seed"),
        Binding("p", "toggle_progress", "Progress panel"),
        Binding("b", "open_in_browser", "Open in browser"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.platform_key = harness_mod.detect_platform()
        self.harness: Optional[harness_mod.Harness] = None
        self.selected_model: Optional[str] = None
        self.remote_models: List[str] = []
        self.selected_remote_model: Optional[str] = None
        self.runs: Dict[str, RunRecord] = {}
        self.run_order: List[str] = []
        self.active_run_id: Optional[str] = None
        self._run_counter = 0
        self._last_meter: Dict[str, float] = {}
        self._stop_requested: Dict[str, bool] = {}
        self._state = _load_tui_state()
        self._state_dirty = False
        self.progress_visible = True
        self._model_routes: Dict[str, Dict[str, str]] = {}

    # ── UI / messages ────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main"):
            with Vertical(id="controls"):
                yield Static("1 · Harness (backend)", classes="section")
                yield Select(
                    [(h.name, h.id) for h in harness_mod.available_harnesses()],
                    id="harness",
                    prompt="Select harness…",
                )
                yield Static("2 · Model", classes="section")
                yield OptionList(id="models")
                yield Static("3 · Creative seed", classes="section")
                yield Input(
                    value=str(self._state.get("seed", "2")),
                    id="seed",
                    type="integer",
                    placeholder="Seed (1-… ) · N randomizes",
                )
                yield Input(
                    placeholder="Base URL override (blank = harness default)",
                    id="custom-url",
                )
                with Horizontal(classes="remote-header"):
                    yield Static("4 · Remote target (SSH)", classes="section")
                    yield Button("▾ hide", id="toggle-remote", variant="default")
                with Vertical(id="remote-box"):
                    yield Input(placeholder="Host / IP, e.g. 192.168.1.50", id="remote-host")
                    yield Input(value="~/gravedancer", id="remote-dir", placeholder="Remote project dir")
                    yield Input(placeholder="SSH user (optional / ssh config)", id="remote-user")
                    yield Input(value="http://127.0.0.1:11434", id="remote-url", placeholder="Remote inference base URL")
                    with Horizontal():
                        yield Button("Test SSH", id="connect", variant="primary")
                        yield Button("Deploy", id="deploy", variant="default")
                    yield Select([], id="remote-models", prompt="Remote models…")
                with Horizontal(id="button-row"):
                    yield Button("Run Local", id="run-local", variant="success")
                    yield Button("Run Remote", id="run-remote", variant="warning")
                    yield Button("Stop", id="stop", variant="error", disabled=True)
                    yield Button("Refresh", id="refresh")
                    yield Button("Health", id="health")
                yield Static("", id="status", markup=True)
            with Vertical(id="output"):
                yield Static("Runs (live)", classes="section", id="runs-header")
                yield OptionList(id="runs")
                yield Static("Progress — select a run", classes="section", id="progress-header")
                yield Static("", id="progress-panel", markup=True)
                yield Static("Log — select a run above", classes="section")
                yield RichLog(id="log", markup=False, wrap=True, auto_scroll=True)
        yield Footer()

    def on_mount(self) -> None:
        available = harness_mod.available_harnesses()
        if not available:
            self._set_status("[red]No harness available on this platform[/]")
            return
        state = self._state
        preferred = str(state.get("harness", "")).strip()
        if preferred not in {h.id for h in available}:
            preferred = "rapid-mlx" if self.platform_key == "darwin" else "ollama"
            if preferred not in {h.id for h in available}:
                preferred = available[0].id
        self.query_one("#harness", Select).value = preferred
        saved_url = str(state.get("base_url", "")).strip()
        if saved_url:
            self.query_one("#custom-url", Input).value = saved_url
        # Remote section starts collapsed unless it was open (or a host is set).
        if not (state.get("remote_open") or str(state.get("remote_host", "")).strip()):
            self._set_remote_box_visible(False)
        self._log(f"Platform {self.platform_key} — harnesses: {', '.join(h.id for h in available)}")
        self.set_interval(1.0, self._tick_runs)

    # ── persisted selections ─────────────────────────────────────────────

    def _persist(self, **changes: Any) -> None:
        """Merge selection changes into the state file (flushed each tick)."""
        self._state.update(changes)
        self._state_dirty = True

    def _flush_state(self) -> None:
        if self._state_dirty:
            _save_tui_state(self._state)
            self._state_dirty = False

    # ── helpers ──────────────────────────────────────────────────────────

    def _set_status(self, text: str) -> None:
        self.query_one("#status", Static).update(text)

    def _log(self, text: str) -> None:
        self.query_one("#log", RichLog).write(text)

    def _current_base(self) -> Optional[str]:
        if self.harness and self.harness.kind == "openai_http":
            return self.query_one("#custom-url", Input).value.strip() or None
        return None

    def _build_target(self) -> Optional[RemoteTarget]:
        host = self.query_one("#remote-host", Input).value.strip()
        if not host:
            self._set_status("[red]Enter a remote host / IP first.[/]")
            return None
        target = RemoteTarget(
            host=host,
            user=self.query_one("#remote-user", Input).value.strip(),
            proj_dir=self.query_one("#remote-dir", Input).value.strip() or "~/gravedancer",
            inference_base=self.query_one("#remote-url", Input).value.strip() or "http://127.0.0.1:11434",
        )
        error = target.validate()
        if error:
            self._set_status(f"[red]Invalid remote target: {error}[/]")
            return None
        return target

    # ── harness / model events ───────────────────────────────────────────

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "harness":
            self.harness = harness_mod.by_id(str(event.value))
            is_http = self.harness.kind == "openai_http"
            url_input = self.query_one("#custom-url", Input)
            url_input.display = is_http
            default_base = self.harness.base_url()
            url_input.placeholder = (
                f"Base URL override (default {default_base})" if default_base
                else "Base URL, e.g. http://192.168.1.50:11434"
            )
            note = self.harness.note or ""
            self._set_status(f"[bold]{self.harness.name}[/] — {note}")
            self._persist(harness=self.harness.id)
            self._load_models()
        elif event.select.id == "remote-models":
            self.selected_remote_model = str(event.value) if event.value else None

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "seed":
            self._persist(seed=event.value)
            try:
                seed_value = int(event.value.strip())
            except ValueError:
                return
            if seed_value < 0:
                return
            seed = generate_creative_seed(seed=seed_value)
            self._set_status(
                f"Seed [bold]{seed_value}[/] → \"[cyan]{seed['title']}[/]\" "
                f"· {seed['num_days']} days · Jedi {seed['jedi_name']}"
            )
        elif event.input.id == "custom-url":
            self._persist(base_url=event.value.strip())
        elif event.input.id == "remote-host":
            self._persist(remote_host=event.value.strip())

    def _set_remote_box_visible(self, visible: bool) -> None:
        self.query_one("#remote-box", Vertical).display = visible
        button = self.query_one("#toggle-remote", Button)
        button.label = "▾ hide" if visible else "▸ show"
        self._persist(remote_open=visible)

    def action_random_seed(self) -> None:
        seed_value = random.randint(1, 99999)
        self.query_one("#seed", Input).value = str(seed_value)

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option_list.id == "models":
            self.selected_model = str(event.option.id)
            harness_name = self.harness.name if self.harness else "?"
            self._set_status(f"Model: [bold cyan]{self.selected_model}[/] · harness: {harness_name}")
            self._persist(model=self.selected_model)
            route = self._model_routes.get(self.selected_model)
            if route and self.harness is not None:
                bases = self._state.setdefault("bases", {}).setdefault(self.harness.id, [])
                if route["base"] not in bases:
                    bases.append(route["base"])
                    self._state_dirty = True
        elif event.option_list.id == "runs":
            self._select_run(str(event.option.id))

    # ── model discovery (local harness) ──────────────────────────────────

    def _load_models(self) -> None:
        if self.harness is None:
            return
        self._models_worker(self.harness)

    @work(thread=True, exclusive=True)
    def _models_worker(self, harness: harness_mod.Harness) -> None:
        base = self._current_base()
        if harness.id == "remote-openai" and not base:
            self.call_from_thread(
                self._set_status,
                "[yellow]Enter a base URL for the remote endpoint, then press Refresh.[/]",
            )
            return
        self.call_from_thread(self._set_status, f"Loading models from {harness.name}…")
        try:
            if harness.kind == "openai_http":
                # Merge every known endpoint for this harness (the override
                # field first), so parallel servers (e.g. e4b + 27B on
                # different ports) appear as one selectable list.
                bases: List[str] = []
                if base:
                    bases.append(base)
                for candidate in harness.all_bases():
                    if candidate not in bases:
                        bases.append(candidate)
                for extra in self._state.get("bases", {}).get(harness.id, []):
                    if extra not in bases:
                        bases.append(extra)
                entries = harness_mod.discover_models_across_bases(bases)
                choices = []
                routes: Dict[str, Dict[str, str]] = {}
                multiple = len({e["base"] for e in entries}) > 1
                served_ids: set = set()
                for entry in entries:
                    label = entry["id"]
                    if multiple:
                        hostport = entry["base"].split("//", 1)[-1]
                        label = f"{entry['id']} @{hostport}"
                    choices.append(label)
                    routes[label] = entry
                    served_ids.add(entry["id"])
                # Locally downloaded checkpoints that no live server is
                # serving still belong in the list: selecting one routes to
                # the default endpoint and load-on-run starts its server.
                fallback_base = base or harness.all_bases()[0] if harness.all_bases() else None
                for name in harness_mod.list_local_model_dirs():
                    if name in served_ids:
                        continue
                    label = f"{name} (on disk)"
                    choices.append(label)
                    if fallback_base:
                        routes[label] = {"base": fallback_base, "id": name}
                self._model_routes = routes
                served_count = len(served_ids)
                disk_count = len(choices) - served_count
                summary = (
                    f"{len(choices)} model(s) on {harness.name}"
                    + (f" ({served_count} served, {disk_count} on disk)" if disk_count else "")
                )
                self.call_from_thread(self._apply_model_choices, choices, summary)
                return
            choices = harness_mod.list_model_choices(harness, base)
        except Exception as exc:
            self.call_from_thread(
                self._set_status, f"[red]Could not list models: {exc}[/]"
            )
            return
        self.call_from_thread(self._apply_model_choices, choices)

    def _apply_model_choices(self, choices: List[str], summary: str = "") -> None:
        model_list = self.query_one("#models", OptionList)
        model_list.clear_options()
        for label in choices:
            model_list.add_option(Option(str(label), id=str(label)))
        if choices:
            saved = str(self._state.get("model", "")).strip()
            restore_index = 0
            if saved:
                for idx, label in enumerate(choices):
                    if str(label) == saved:
                        restore_index = idx
                        break
            model_list.highlighted = restore_index
            self.selected_model = str(choices[restore_index])
        self._set_status(
            summary or f"{len(choices)} model(s) on {self.harness.name if self.harness else '?'}"
        )

    def action_refresh_models(self) -> None:
        self._load_models()

    # ── health check (local harness) ─────────────────────────────────────

    def _health_check(self) -> None:
        harness = self.harness
        if harness is None:
            return
        base = self._current_base()
        self._set_status(f"Checking {harness.name}…")
        self._health_worker(harness, base)

    @work(thread=True, exclusive=True)
    def _health_worker(self, harness: harness_mod.Harness, base: Optional[str]) -> None:
        result = harness_mod.health_check(harness, base)
        models = ", ".join(result.get("models", [])[:8]) or "(none)"
        if result["ok"]:
            message = (
                f"[bold green]✓ {harness.name} reachable[/] · "
                f"{len(result.get('models', []))} model(s): {models}"
            )
        else:
            message = (
                f"[bold red]✗ {harness.name} unreachable[/] — {result.get('error')}"
            )
        self.call_from_thread(self._set_status, message)

    # ── remote SSH actions ───────────────────────────────────────────────

    def _connect_remote(self) -> None:
        target = self._build_target()
        if target is None:
            return
        self._set_status(f"Testing SSH to {target.hostspec()}…")
        self._connect_worker(target)

    @work(thread=True, exclusive=True)
    def _connect_worker(self, target: RemoteTarget) -> None:
        result = remoter_mod.test_connection(target)
        if not result["ok"]:
            self.call_from_thread(
                self._set_status,
                f"[bold red]✗ {target.host} unreachable[/] — {result.get('error')}",
            )
            return
        info = remoter_mod.remote_info(target)
        models = remoter_mod.remote_models(target)
        self.call_from_thread(self._apply_remote_info, target, info, models)

    def _apply_remote_info(self, target: RemoteTarget, info: dict, models: List[str]) -> None:
        py = info.get("__PY__", "?")
        venv = info.get("__VENV__", "?")
        ollama = info.get("__OLLAMA__", "?")
        self.remote_models = models
        sel = self.query_one("#remote-models", Select)
        sel.set_options([(m, m) for m in models])
        self.selected_remote_model = models[0] if models else None
        self._set_status(
            f"[bold green]✓ {target.host} connected[/]"
            + (f" · ollama: {ollama}" if "missing" not in str(ollama) else f" · [red]ollama missing[/]")
            + f" · venv: {venv} · python3: {py}"
        )

    def _deploy_remote(self) -> None:
        target = self._build_target()
        if target is None:
            return
        self._set_status(f"Deploying to {target.hostspec()}…")
        self._deploy_worker(target)

    @work(thread=True, exclusive=True)
    def _deploy_worker(self, target: RemoteTarget) -> None:
        result = remoter_mod.deploy(target)
        steps = " | ".join(str(s) for s in result.get("steps", []))
        models = remoter_mod.remote_models(target)
        self.call_from_thread(
            self._apply_deploy_result, target, result, steps, models
        )

    def _apply_deploy_result(self, target: RemoteTarget, result: dict, steps: str, models: List[str]) -> None:
        self.remote_models = models
        sel = self.query_one("#remote-models", Select)
        sel.set_options([(m, m) for m in models])
        self.selected_remote_model = models[0] if models else None
        if result["ok"]:
            self._set_status(f"[bold green]✓ Deployed to {target.host}[/]\n{steps}")
        else:
            self._set_status(f"[bold red]✗ Deploy failed[/]\n{steps}\n{result.get('error', '')}")

    # ── runs list ────────────────────────────────────────────────────────

    def _new_run_id(self) -> str:
        self._run_counter += 1
        return f"run-{self._run_counter}"

    def _register_run(self, record: RunRecord) -> None:
        self.runs[record.run_id] = record
        self.run_order.append(record.run_id)
        self._stop_requested[record.run_id] = False
        self._select_run(record.run_id)
        self.query_one("#stop", Button).disabled = False

    def _run_label(self, record: RunRecord) -> str:
        symbol = _STATUS_SYMBOLS.get(record.status, "·")
        label = record.label
        if record.status == "running":
            dur = max(0, time.perf_counter() - record.started)
            # Compact form: the harness prefix is implied while streaming and
            # the freed width goes to the progress bar + stage.
            if " · " in label:
                parts = label.split(" · ")
                label = " · ".join(parts[-2:])
            suffix = f"  {record.progress.label_suffix()}"
        else:
            dur = (record.ended or record.started) - record.started
            suffix = f"  [{_progress_bar(record.progress.pct)}] {record.progress.pct:.0f}%"
            if record.status == "error" and record.error_tail:
                suffix += f" · {record.error_tail}"
        return f"{symbol} {label}  [{dur:6.0f}s]{suffix}"

    def _tick_runs(self) -> None:
        runs = self.query_one("#runs", OptionList)
        for run_id in self.run_order:
            record = self.runs.get(run_id)
            if record is None:
                continue
            try:
                runs.replace_option_prompt(run_id, self._run_label(record))
            except Exception:
                pass
        self._update_runs_header()
        self._flush_state()
        self._render_progress_panel()

    def _render_progress_panel(self) -> None:
        panel = self.query_one("#progress-panel", Static)
        header = self.query_one("#progress-header", Static)
        if not self.progress_visible:
            return
        record = self.runs.get(self.active_run_id or "")
        if record is None:
            panel.update("No run selected.")
            header.update("Progress — select a run")
            return
        elapsed = (record.ended or time.perf_counter()) - record.started
        panel.update(record.progress.render_tree(elapsed))
        state_word = record.status
        header.update(f"Progress — {record.label} [{state_word}]")

    def action_toggle_progress(self) -> None:
        self.progress_visible = not self.progress_visible
        panel = self.query_one("#progress-panel", Static)
        panel.add_class("hidden") if not self.progress_visible else panel.remove_class("hidden")
        if self.progress_visible:
            self._render_progress_panel()

    def _update_runs_header(self) -> None:
        counts: Dict[str, int] = {}
        for record in self.runs.values():
            counts[record.status] = counts.get(record.status, 0) + 1
        if not self.runs:
            header = "Runs (live)"
        else:
            parts = []
            if counts.get("running"):
                parts.append(f"[bold green]{counts['running']} running[/]")
            if counts.get("stopping"):
                parts.append(f"[yellow]{counts['stopping']} stopping[/]")
            if counts.get("finished"):
                parts.append(f"{counts['finished']} finished")
            if counts.get("error"):
                parts.append(f"[red]{counts['error']} failed[/]")
            if counts.get("stopped"):
                parts.append(f"{counts['stopped']} stopped")
            header = "Runs (live) — " + " · ".join(parts) if parts else "Runs (live)"
        self.query_one("#runs-header", Static).update(header)

    def _shutdown_spawned_server(self, record: RunRecord) -> None:
        """Kill a TUI-spawned server after its run ends.

        Servers the user started manually are never touched (no proc ref).
        If another still-active run shares this server, it stays up until
        that run finishes too.
        """
        for other_id in self.run_order:
            other = self.runs.get(other_id)
            if other is record or other is None:
                continue
            if (other.status in ("running", "stopping")
                    and other.server_base == record.server_base):
                self._log(f"[server] {record.server_model} left running — "
                          f"shared by {other.label}")
                return
        proc = record.server_proc

        def kill() -> None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except (OSError, ProcessLookupError):
                try:
                    proc.terminate()
                except Exception:
                    pass

        self._escalate_local(kill)
        self._log(f"[server] shutting down {record.server_model} on {record.server_base}")

    def _select_run(self, run_id: str) -> None:
        self.active_run_id = run_id
        record = self.runs.get(run_id)
        if record is None:
            return
        log = self.query_one("#log", RichLog)
        log.clear()
        for line in record.lines:
            log.write(line)
        if record.status == "running":
            self._set_status(
                f"[bold]{record.label}[/] · {record.status} · streaming…"
                + (f"\n[dim]{record.activity}[/]" if record.activity else "")
            )
        else:
            self._set_status(
                f"[bold]{record.label}[/] · {record.status}"
                + (f" (exit {record.code})" if record.code is not None else "")
            )
        try:
            log.scroll_end()
        except Exception:
            pass

    def on_run_line(self, event: RunLine) -> None:
        record = self.runs.get(event.run_id)
        if record is None:
            return
        record.lines.append(event.text)
        if event.run_id == self.active_run_id:
            self._log(event.text)

    def on_run_done(self, event: RunDone) -> None:
        record = self.runs.get(event.run_id)
        if record is None:
            return
        if self._stop_requested.get(event.run_id):
            record.status = "stopped"
        elif event.code == 0:
            record.status = "finished"
        else:
            record.status = "error"
        record.ended = time.perf_counter()
        for line in record.lines:
            match = _EPISODE_ID_RE.search(line)
            if match:
                record.episode_id = match.group(1).strip("/")
                break
        if record.server_proc is not None:
            self._shutdown_spawned_server(record)
        tail = "\n".join(record.lines[-6:])
        if record.status == "finished":
            summary = "\n".join(
                l.strip()
                for l in record.lines
                if any(m in l for m in ("TOTAL PIPELINE", "Episode saved:", "Episode ID:"))
            )
            hint = " · press [bold]o[/] to read it" if record.episode_id else ""
            if event.run_id == self.active_run_id:
                self._log(f"\n✓ Finished (exit 0).{('' )}"
                          + (f"\n{summary}" if summary else ""))
            self._set_status(
                f"[bold green]Done ✓[/] {record.label}" + (f"\n{summary}" if summary else "")
                + (f"\n[bold]o[/]: open episode · [bold]v[/]: library" if record.episode_id else "")
            )
        elif record.status == "stopped":
            self._set_status(f"[yellow]Stopped[/] {record.label}")
        else:
            tail = next(
                (line.strip() for line in reversed(record.lines)
                 if line.strip() and not _METER_RE.search(line)),
                "",
            )
            record.error_tail = tail[-70:]
            self._set_status(
                f"[bold red]Failed (exit {event.code})[/] {record.label}"
                + (f"\n[dim]{record.error_tail}[/]" if record.error_tail else "")
            )
        self._update_stop_button()
        self._tick_runs()

    def _update_stop_button(self) -> None:
        any_running = any(r.status == "running" for r in self.runs.values())
        self.query_one("#stop", Button).disabled = not any_running

    # ── starting runs ────────────────────────────────────────────────────

    def action_run_local(self) -> None:
        harness = self.harness
        model = self.selected_model
        if harness is None or not model:
            self._set_status("[red]Select a harness and a model first.[/]")
            return
        seed = self._parse_seed()
        if seed is None:
            return
        # Route to the exact server this model was discovered on (multi-server
        # discovery labels options "model @host:port"); fall back to the
        # harness default when the model came from a non-HTTP source.
        route = self._model_routes.get(model)
        real_model = route["id"] if route else model
        route_base = route["base"] if route else None
        ref = harness_mod.pipeline_model_ref(harness, real_model)
        env = os.environ.copy()
        env.update(harness_mod.pipeline_environment(harness, route_base or self._current_base()))
        env["GRAVEDANCER_MODEL"] = ref
        if harness.kind == "opencode_cli":
            # Hosted models are not memory-bound: raise the per-section cap so
            # a 5-chapter day can reach the ~45k-token daily target instead of
            # stalling at the local 4500-token ceiling.
            env.setdefault("GRAVEDANCER_SECTION_MAX_TOKENS", "12000")
        command = [
            sys.executable,
            "-u",
            str(PROJECT_ROOT / "run_creative_pipeline.py"),
            "--seed",
            str(seed),
            "--model",
            ref,
        ]
        record = RunRecord(
            run_id=self._new_run_id(),
            label=f"local · {harness.name} · {model} · s{seed}",
            local=True,
            seed=seed,
            started=time.perf_counter(),
        )
        spec = {
            "harness": harness,
            "real_model": real_model,
            "base": route_base,
            "env": env,
            "command": command,
        }
        self._register_run(record)
        self._flush_state()
        self.query_one("#log", RichLog).clear()
        if harness.kind == "openai_http" and route_base:
            self._launch_worker(record, spec)
        else:
            self._spawn_pipeline(record, spec)

    def _spawn_pipeline(self, record: RunRecord, spec: Dict[str, Any]) -> None:
        proc = subprocess.Popen(
            spec["command"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=spec["env"],
            cwd=str(PROJECT_ROOT),
            start_new_session=True,
        )
        record.popen = proc
        record.started = time.perf_counter()
        self._stream_worker(record)

    @work(thread=True)
    def _launch_worker(self, record: RunRecord, spec: Dict[str, Any]) -> None:
        """Ensure the target server is up and serving the model, then launch.

        Implements load-on-run for local HTTP servers: when the route's model
        is not being served (or the server is down), spawn `rapid-mlx serve`
        for it from the on-disk checkpoint and wait for readiness before
        starting the pipeline. Servers stay warm afterwards for instant reuse.
        """
        base = spec["base"]
        real_model = spec["real_model"]
        harness = spec["harness"]

        def log(text: str) -> None:
            self.call_from_thread(self._log, text)

        if server_serves(base, real_model):
            log(f"[server] {harness.name} already serving {real_model} at {base}")
            self.call_from_thread(self._spawn_pipeline, record, spec)
            return

        port = port_of(base)
        model_path = find_model_disk_path(real_model)
        if model_path is None:
            record.status = "error"
            record.ended = time.perf_counter()
            record.error_tail = f"no local checkpoint for {real_model}"
            log(f"[server] ✗ {record.error_tail}; start its server manually and retry.")
            self.post_message(RunDone(record.run_id, -1))
            return

        binary = os.environ.get("GRAVEDANCER_RAPIDMLX_BIN", "rapid-mlx")
        server_cmd = [
            binary, "serve", str(model_path),
            "--served-model-name", real_model,
            "--port", str(port), "--no-mllm",
            "--cache-memory-percent", "0.35",
        ]
        log(f"[server] starting {real_model} on :{port} "
            f"(~16 GB models take 20-90s to load)…")
        try:
            proc = subprocess.Popen(
                server_cmd, cwd=str(PROJECT_ROOT),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            record.server_proc = proc
            record.server_base = base
            record.server_model = real_model
        except OSError as exc:
            record.status = "error"
            record.ended = time.perf_counter()
            record.error_tail = f"could not start {binary}: {exc}"
            log(f"[server] ✗ {record.error_tail}")
            self.post_message(RunDone(record.run_id, -1))
            return

        deadline = time.time() + 300
        while time.time() < deadline:
            if server_serves(base, real_model):
                log(f"[server] ✓ {real_model} ready at {base}")
                self.call_from_thread(self._spawn_pipeline, record, spec)
                return
            time.sleep(3)
        record.status = "error"
        record.ended = time.perf_counter()
        record.error_tail = f"server on :{port} not ready after 300s"
        log(f"[server] ✗ {record.error_tail} — check log/ for its output.")
        self.post_message(RunDone(record.run_id, -1))

    def action_run_remote(self) -> None:
        host = self.query_one("#remote-host", Input).value.strip()
        model = self.selected_remote_model
        seed = self._parse_seed()
        if not host:
            self._set_status("[red]Enter a remote host first.[/]")
            return
        if not model:
            self._set_status("[red]Select a remote model first (Test/Deploy SSH).[/]")
            return
        target = self._build_target()
        if target is None:
            return
        ref = f"lmstudio:{model}"
        extra_env = {"MODEL_REF": ref}
        run_token = uuid.uuid4().hex[:12]
        proc = remoter_mod.start_remote(target, extra_env, str(seed), run_token=run_token)
        record = RunRecord(
            run_id=self._new_run_id(),
            label=f"remote {target.host} · {model} · s{seed}",
            local=False,
            seed=seed,
            started=time.perf_counter(),
            popen=proc,
            target=target,
            marker=f"run_creative_pipeline.py --run-token {run_token}",
        )
        self._register_run(record)
        self._stream_worker(record)
        self._flush_state()
        self.query_one("#log", RichLog).clear()

    def _parse_seed(self) -> Optional[int]:
        raw = self.query_one("#seed", Input).value.strip()
        try:
            return int(raw)
        except ValueError:
            self._set_status(f"[red]Invalid seed: {raw!r}[/]")
            return None

    # ── episode viewer ───────────────────────────────────────────────────

    def action_open_viewer(self) -> None:
        self.app.push_screen(EpisodeViewerScreen())

    def action_open_last_episode(self) -> None:
        finished = [self.runs[rid] for rid in self.run_order if self.runs[rid].episode_id]
        if not finished:
            self._set_status("[yellow]No finished run has produced an episode yet.[/]")
            return
        episode_id = finished[-1].episode_id
        self._set_status(f"Opening [bold cyan]{episode_id}[/] · esc returns")
        self.app.push_screen(EpisodeViewerScreen(highlight_episode=episode_id))

    def _latest_episode_id(self) -> Optional[str]:
        finished = [self.runs[rid] for rid in self.run_order if self.runs[rid].episode_id]
        if finished:
            return finished[-1].episode_id
        try:
            episodes = sorted(
                (p for p in SETTINGS.storage_path.iterdir()
                 if p.is_dir() and (p / "metadata.json").is_file()),
                key=lambda p: p.name, reverse=True,
            )
            return episodes[0].name if episodes else None
        except OSError:
            return None

    def action_open_in_browser(self) -> None:

        episode_id = self._latest_episode_id()
        if not episode_id:
            self._set_status("[yellow]No episodes to preview yet.[/]")
            return
        path = write_episode_html(SETTINGS.storage_path, episode_id)
        if path is None:
            self._set_status("[yellow]Episode has no story.md yet.[/]")
            return
        webbrowser.open(path.as_uri())
        self._set_status(f"[green]Opened in browser:[/] {path}")

    # ── streaming / stopping ─────────────────────────────────────────────

    @work(thread=True)
    def _stream_worker(self, record: RunRecord) -> None:
        proc = record.popen
        if proc is None or proc.stdout is None:
            self.post_message(RunDone(record.run_id, -1))
            return
        while True:
            raw_line = proc.stdout.readline()
            if not raw_line:
                break
            text = _ANSI_RE.sub("", raw_line)
            clean = next(
                (p.rstrip() for p in reversed(re.split(r"[\r\n]+", text)) if p.strip()),
                "",
            )
            if not clean:
                continue
            # Every line feeds the progress model (meters carry per-section
            # token counts); meters then stay out of the shared log.
            record.progress.update(clean)
            if _METER_RE.search(clean):
                now = time.perf_counter()
                if now - self._last_meter.get(record.run_id, 0.0) >= 1.5:
                    self._last_meter[record.run_id] = now
                    record.activity = clean.strip()
                continue
            self.post_message(RunLine(record.run_id, clean.strip()))
        code = proc.wait()
        record.code = code
        record.ended = time.perf_counter()
        self.post_message(RunDone(record.run_id, code))

    def action_stop_run(self) -> None:
        if self.active_run_id is None:
            return
        self._stop_run(self.active_run_id)

    def action_quit(self) -> None:
        # Best-effort cleanup so quitting does not orphan detached pipeline
        # processes holding unified memory. Local runs get SIGTERM (the
        # pipeline checkpoints completed days); remote ssh clients are closed.
        for record in self.runs.values():
            if record.status != "running" or record.popen is None:
                continue
            try:
                if record.local:
                    os.killpg(os.getpgid(record.popen.pid), signal.SIGTERM)
                else:
                    record.popen.terminate()
            except (OSError, ProcessLookupError):
                try:
                    record.popen.terminate()
                except OSError:
                    pass
        self.exit()

    def _stop_run(self, run_id: str) -> None:
        record = self.runs.get(run_id)
        if record is None or record.popen is None:
            return
        record.status = "stopping"
        self._stop_requested[run_id] = True
        proc = record.popen
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except (OSError, ProcessLookupError):
            try:
                proc.terminate()
            except OSError:
                pass
        if record.local:
            self._schedule_local_kill(record)
        else:
            self._schedule_remote_kill(record)

    def _schedule_local_kill(self, record: RunRecord) -> None:
        def escalate() -> None:
            time.sleep(4)
            if record.status == "stopping" and record.popen and record.popen.poll() is None:
                try:
                    os.killpg(os.getpgid(record.popen.pid), signal.SIGKILL)
                except (OSError, ProcessLookupError):
                    try:
                        record.popen.kill()
                    except OSError:
                        pass

        self._escalate_local(escalate)

    @work(thread=True)
    def _escalate_local(self, fn) -> None:
        fn()

    def _schedule_remote_kill(self, record: RunRecord) -> None:
        self._remote_pkill_worker(record)

    @work(thread=True)
    def _remote_pkill_worker(self, record: RunRecord) -> None:
        time.sleep(2)
        if record.target is not None and record.marker:
            remoter_mod.remote_pkill(record.target, record.marker)

    # ── buttons ──────────────────────────────────────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "refresh":
            self._load_models()
        elif button_id == "health":
            self._health_check()
        elif button_id == "run-local":
            self.action_run_local()
        elif button_id == "run-remote":
            self.action_run_remote()
        elif button_id == "stop":
            self.action_stop_run()
        elif button_id == "connect":
            self._connect_remote()
        elif button_id == "deploy":
            self._deploy_remote()
        elif button_id == "toggle-remote":
            box = self.query_one("#remote-box", Vertical)
            self._set_remote_box_visible(not box.display)

    # ── quit guard ───────────────────────────────────────────────────────

    def action_quit(self) -> None:
        active = [r for r in self.runs.values() if r.status in ("running", "stopping")]
        if not active:
            self.exit()
            return
        self.push_screen(QuitConfirmScreen(len(active)), self._handle_quit_choice)

    def _handle_quit_choice(self, choice: Optional[str]) -> None:
        if choice == "keep":
            self.exit()
        elif choice == "kill":
            for run_id in list(self.run_order):
                record = self.runs.get(run_id)
                if record and record.status in ("running", "stopping"):
                    self._stop_run(run_id)
            self.set_timer(1.5, self.exit)
        # "cancel" / None: stay in the app


if __name__ == "__main__":
    GravedancerTUI().run()