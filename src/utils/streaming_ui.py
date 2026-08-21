"""Helpers for routing streamed generation text into UI panels."""

import time

from src.utils._streamlit_fallback import st

STREAM_PANEL_KEYS = ("stage_label", "progress_log", "outline_live", "day_live", "section_live")


def _friendly_stage_name(stage: str) -> str:
    if stage.startswith("outline"):
        return "Outline"
    if "continuity" in stage:
        return "Continuity"
    if "section" in stage:
        return "Section"
    if stage.startswith("day"):
        return "Day"
    return stage.title()


def reset_stream_panels(widgets: dict[str, object], progress_state: dict[str, object] | None = None) -> None:
    """Clear live stream panels and state before a new generation run starts."""
    for key in STREAM_PANEL_KEYS:
        widget = widgets.get(key)
        if widget:
            widget.empty()
    if progress_state is not None:
        progress_state.clear()
        progress_state.update(build_progress_state())


def build_progress_state() -> dict[str, object]:
    """Create the canonical initial progress-state payload."""
    return {
        "events": [],
        "current_stage": "Idle",
        "started_at": time.monotonic(),
        "chars_generated": 0,
        "approx_tokens": 0,
        "target_tokens": 0,
    }


def build_stream_runtime(streamlit_module=None) -> dict[str, object]:
    """Create both the live-monitor widgets and the matching initial state."""
    module = streamlit_module or st
    if module is None:
        raise RuntimeError("streamlit is required to build stream widgets")
    return {
        "widgets": {key: module.empty() for key in STREAM_PANEL_KEYS},
        "progress_state": build_progress_state(),
    }


def render_cached_outline_banner(widgets: dict[str, object], outline: str) -> None:
    """Render the resume banner for a cached outline."""
    stage_line, progress_line = _build_cached_outline_lines()
    stage_label = widgets.get("stage_label")
    if stage_label:
        stage_label.markdown(stage_line)
    progress_log = widgets.get("progress_log")
    if progress_log:
        progress_log.markdown(progress_line)
    outline_live = widgets.get("outline_live")
    if outline_live:
        outline_live.markdown(f"#### Live Outline\n```markdown\n{outline}\n```")


def _build_cached_outline_lines() -> tuple[str, str]:
    """Build the shared text used when resuming from a cached outline."""
    return (
        "**Outline**: Resuming from cached outline.",
        "- **Outline**: Resuming from cached outline.",
    )


def _build_progress_log_lines(progress_state: dict[str, object], extra_line: str | None = None) -> list[str]:
    """Build the text shown in the progress panel."""
    events = progress_state.get("events", [])
    current_stage = progress_state.get("current_stage", "Idle")
    started_at = progress_state.get("started_at")
    elapsed = max(0.0, time.monotonic() - started_at) if isinstance(started_at, (int, float)) else 0.0
    chars = int(progress_state.get("chars_generated", 0) or 0)
    approx_tokens = int(progress_state.get("approx_tokens", 0) or 0)
    rate = approx_tokens / elapsed if elapsed > 0 else 0.0
    target_tokens = int(progress_state.get("target_tokens", 0) or 0)
    progress_line = ""
    if target_tokens:
        percent = min(100.0, approx_tokens / target_tokens * 100)
        remaining = max(0, target_tokens - approx_tokens)
        eta = remaining / rate if rate > 0 else 0
        progress_line = f" · **Target:** {percent:.1f}% · **ETA:** {_format_elapsed(eta)}"
    log_lines = [
        f"**Current Phase:** {current_stage}",
        f"**Elapsed:** {_format_elapsed(elapsed)} · **Output:** ~{approx_tokens:,} tokens ({chars:,} chars){progress_line}",
        f"**Throughput:** {rate:.1f} tokens/sec · **Progress Events:** {len(events)}",
    ]
    log_lines.extend(f"- {line}" for line in events[-8:])
    if extra_line:
        log_lines.append(f"- {extra_line}")
    return log_lines


def _build_stage_line(stage: str, message: str) -> str:
    """Build the headline line shown at the top of the live monitor."""
    return f"**Current Phase:** {stage} - {message}"


def render_stream_update(stage: str, message: str, text: str, widgets: dict[str, object], progress_state: dict[str, object]) -> None:
    """Route streamed generation updates into the live UI panels."""
    friendly = _friendly_stage_name(stage)
    events = progress_state.setdefault("events", [])
    progress_state["current_stage"] = friendly
    if text:
        chars = len(text)
        progress_state["chars_generated"] = max(int(progress_state.get("chars_generated", 0) or 0), chars)
        # A conservative approximation suitable for an operational display,
        # not billing or quality measurement.
        progress_state["approx_tokens"] = max(0, round(chars / 4))
    events.append(f"{len(events) + 1}. **{friendly}**: {message}")
    stage_label = widgets.get("stage_label")
    if stage_label:
        stage_label.markdown(_build_stage_line(friendly, message))
    progress_log = widgets.get("progress_log")
    if progress_log:
        progress_log.markdown("\n".join(_build_progress_log_lines(progress_state)))
    if not text:
        return
    if stage.startswith("outline"):
        outline_live = widgets.get("outline_live")
        if outline_live:
            outline_live.markdown(f"#### Live Outline\n```markdown\n{text}\n```")
    elif "section" in stage:
        section_live = widgets.get("section_live")
        if section_live:
            section_live.markdown(f"#### Live Section Draft\n```markdown\n{text}\n```")
    else:
        day_live = widgets.get("day_live")
        if day_live:
            day_live.markdown(f"#### Live Day Draft\n```markdown\n{text}\n```")


def finalize_stream_state(
    widgets: dict[str, object],
    progress_state: dict[str, object],
    message: str = "Generation complete.",
    character_count: int | None = None,
) -> None:
    """Mark the live monitor as finished."""
    progress_state["current_stage"] = "Complete"
    if character_count is not None:
        message = f"{message} ({character_count:,} chars)"
    stage_label = widgets.get("stage_label")
    if stage_label:
        stage_label.markdown(f"**Current Phase:** Complete - {message}")
    progress_log = widgets.get("progress_log")
    if progress_log:
        progress_log.markdown("\n".join(_build_progress_log_lines(progress_state, extra_line=message)))


def _format_elapsed(seconds: float) -> str:
    """Format elapsed seconds for a compact live-generation display."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes, remainder = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m {remainder:02d}s"
