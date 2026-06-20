"""Helpers for routing streamed generation text into UI panels."""

from typing import Dict, List

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


def reset_stream_panels(widgets: Dict[str, object], progress_state: Dict[str, object] | None = None) -> None:
    """Clear live stream panels and state before a new generation run starts."""
    for key in STREAM_PANEL_KEYS:
        widget = widgets.get(key)
        if widget:
            widget.empty()
    if progress_state is not None:
        progress_state.clear()
        progress_state.update(build_progress_state())


def build_progress_state() -> Dict[str, object]:
    """Create the canonical initial progress-state payload."""
    return {"events": [], "current_stage": "Idle"}


def build_stream_runtime(streamlit_module=None) -> Dict[str, object]:
    """Create both the live-monitor widgets and the matching initial state."""
    module = streamlit_module or st
    if module is None:
        raise RuntimeError("streamlit is required to build stream widgets")
    return {
        "widgets": {key: module.empty() for key in STREAM_PANEL_KEYS},
        "progress_state": build_progress_state(),
    }


def render_cached_outline_banner(widgets: Dict[str, object], outline: str) -> None:
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


def _build_progress_log_lines(progress_state: Dict[str, object], extra_line: str | None = None) -> List[str]:
    """Build the text shown in the progress panel."""
    events = progress_state.get("events", [])
    current_stage = progress_state.get("current_stage", "Idle")
    log_lines = [f"**Current Phase:** {current_stage}", f"**Progress Events:** {len(events)}"]
    log_lines.extend(f"- {line}" for line in events[-8:])
    if extra_line:
        log_lines.append(f"- {extra_line}")
    return log_lines


def _build_stage_line(stage: str, message: str) -> str:
    """Build the headline line shown at the top of the live monitor."""
    return f"**Current Phase:** {stage} - {message}"


def render_stream_update(stage: str, message: str, text: str, widgets: Dict[str, object], progress_state: Dict[str, object]) -> None:
    """Route streamed generation updates into the live UI panels."""
    friendly = _friendly_stage_name(stage)
    events = progress_state.setdefault("events", [])
    progress_state["current_stage"] = friendly
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
    widgets: Dict[str, object],
    progress_state: Dict[str, object],
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
