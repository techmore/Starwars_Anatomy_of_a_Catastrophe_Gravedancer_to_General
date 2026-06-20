"""Pipeline timeline component for tracking multi-stage generation progress.

Renders a horizontal timeline of all pipeline stages with visual status
(pending / active / done / error) that updates in real-time as each
stage progresses.  Tracks start/end timestamps and durations for each
completed stage.
"""

import time
from typing import List, Dict, Optional

from src.utils._streamlit_fallback import st


PIPELINE_STAGES = [
    ("concept", "Concept", "1"),
    ("extraction", "Extract", "2"),
    ("repair", "Repair", "3"),
    ("outline", "Outline", "4"),
    ("story", "Story", "5"),
    ("critique", "Critique", "6"),
    ("save", "Save", "7"),
]

_STAGE_KEYS = [s[0] for s in PIPELINE_STAGES]


class PipelineTracker:
    """Tracks timestamps and durations for each pipeline stage.

    Call :meth:`start` when a stage begins and :meth:`complete` when it
    finishes.  The :meth:`timings` dict can be passed to
    :func:`render_pipeline_timeline` to display durations under each step.
    """

    def __init__(self) -> None:
        self._start_times: Dict[str, float] = {}
        self._end_times: Dict[str, float] = {}
        self._stage_start_wall: Dict[str, float] = {}
        self._stage_end_wall: Dict[str, float] = {}
        self._global_start: float = time.perf_counter()
        self._global_start_wall: float = time.time()
        self._global_end: Optional[float] = None
        self._global_end_wall: Optional[float] = None

    def start(self, stage: str) -> None:
        """Record the start time for *stage*."""
        self._start_times[stage] = time.perf_counter()
        self._stage_start_wall[stage] = time.time()

    def complete(self, stage: str) -> None:
        """Record the end time for *stage*."""
        assert stage in self._start_times, f"complete('{stage}') called without start()"
        self._end_times[stage] = time.perf_counter()
        self._stage_end_wall[stage] = time.time()

    def global_stop(self) -> None:
        """Stop the global pipeline timer."""
        self._global_end = time.perf_counter()
        self._global_end_wall = time.time()

    def duration(self, stage: str) -> Optional[float]:
        """Return the elapsed seconds for *stage*, or None if incomplete."""
        s = self._start_times.get(stage)
        e = self._end_times.get(stage)
        if s is not None and e is not None:
            return e - s
        return None

    def cumulative_offset(self, stage: str) -> Optional[float]:
        """Return seconds from global start to this stage's start, or None."""
        s = self._start_times.get(stage)
        if s is not None:
            return s - self._global_start
        return None

    @property
    def timings(self) -> Dict[str, float]:
        """Return a ``{stage: seconds}`` dict for all completed stages."""
        return {
            stage: dur
            for stage in _STAGE_KEYS
            if (dur := self.duration(stage)) is not None
        }

    @property
    def global_elapsed(self) -> float:
        """Total elapsed seconds from global start to now or global stop."""
        end = self._global_end or time.perf_counter()
        return end - self._global_start

    @property
    def global_elapsed_str(self) -> str:
        return _fmt_duration(self.global_elapsed)

    @property
    def start_time_str(self) -> str:
        return time.strftime("%H:%M:%S", time.localtime(self._global_start_wall))

    @property
    def end_time_str(self) -> str:
        if self._global_end_wall is not None:
            return time.strftime("%H:%M:%S", time.localtime(self._global_end_wall))
        return ""

    def format_duration(self, stage: str) -> str:
        """Return a human-readable duration string for *stage*."""
        dur = self.duration(stage)
        if dur is None:
            return ""
        return _fmt_duration(dur)

    def format_stage_start(self, stage: str) -> str:
        """Return wall-clock start time for *stage*, or empty."""
        t = self._stage_start_wall.get(stage)
        if t is None:
            return ""
        return time.strftime("%H:%M:%S", time.localtime(t))

    def format_stage_end(self, stage: str) -> str:
        """Return wall-clock end time for *stage*, or empty."""
        t = self._stage_end_wall.get(stage)
        if t is None:
            return ""
        return time.strftime("%H:%M:%S", time.localtime(t))


def _fmt_duration(seconds: float) -> str:
    """Format a duration in seconds as a compact string."""
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    secs = seconds % 60
    if minutes < 60:
        return f"{minutes}m{secs:.0f}s"
    hours = int(minutes // 60)
    mins = minutes % 60
    return f"{hours}h{mins}m"


def render_pipeline_timeline(
    active_stage: str,
    completed_stages: Optional[List[str]] = None,
    error_stage: Optional[str] = None,
    tracker: Optional[PipelineTracker] = None,
    widget=None,
) -> None:
    """Render the horizontal pipeline timeline.

    Parameters:
        active_stage: The stage currently in progress (e.g. "outline").
        completed_stages: List of stage keys that have finished successfully.
        error_stage: The stage that failed (if any).
        tracker: A :class:`PipelineTracker` with timing data.  When provided,
            durations are shown under completed stages and an elapsed time
            under the active stage.
        widget: A ``st.empty()`` placeholder to render into.
    """
    completed = set(completed_stages or [])
    if tracker is not None and active_stage == "" and not error_stage:
        tracker.global_stop()
    html = _build_timeline_html(active_stage, completed, error_stage, tracker)
    if widget is not None:
        widget.markdown(html, unsafe_allow_html=True)
    elif st is not None:
        st.markdown(html, unsafe_allow_html=True)


def _build_timeline_html(
    active_stage: str,
    completed: set,
    error_stage: Optional[str],
    tracker: Optional[PipelineTracker],
) -> str:
    """Build the HTML for the pipeline timeline."""
    steps_html: List[str] = []
    for i, (key, label, num) in enumerate(PIPELINE_STAGES):
        if key == error_stage:
            cls = "error"
            icon = "!"
            time_html = '<div class="pipeline-time">&nbsp;</div>'
        elif key in completed:
            cls = "done"
            icon = "&#10003;"
            dur = tracker.format_duration(key) if tracker else ""
            start_t = tracker.format_stage_start(key) if tracker else ""
            end_t = tracker.format_stage_end(key) if tracker else ""
            clock = f'{start_t}→{end_t}' if start_t and end_t else ""
            if dur or clock:
                time_html = (
                    f'<div class="pipeline-time">'
                    f'<div class="pipeline-dur">{dur}</div>'
                    f'<div class="pipeline-clock">{clock}</div>'
                    f'</div>'
                )
            else:
                time_html = '<div class="pipeline-time">&nbsp;</div>'
        elif key == active_stage:
            cls = "active"
            icon = num
            dur = ""
            clock = ""
            if tracker and key in tracker._start_times:
                elapsed = time.perf_counter() - tracker._start_times[key]
                dur = _fmt_duration(elapsed)
                start_t = tracker.format_stage_start(key)
                if start_t:
                    clock = f'{start_t}→'
            time_html = (
                f'<div class="pipeline-time">'
                f'<div class="pipeline-dur">{dur}</div>'
                f'<div class="pipeline-clock">{clock}</div>'
                f'</div>'
            ) if dur or clock else '<div class="pipeline-time">&nbsp;</div>'
        else:
            cls = ""
            icon = num
            time_html = '<div class="pipeline-time">&nbsp;</div>'

        steps_html.append(
            f'<div class="pipeline-step {cls}">'
            f'<div class="pipeline-dot">{icon}</div>'
            f'<div class="pipeline-label">{label}</div>'
            f'{time_html}'
            f'</div>'
        )
        if i < len(PIPELINE_STAGES) - 1:
            steps_html.append(
                '<div class="pipeline-connector">'
                '<div class="pipeline-connector-line"></div>'
                '</div>'
            )

    # Pipeline summary footer
    summary_parts = []
    if tracker:
        summary_parts.append(
            f'<span class="pipeline-summary-item">'
            f'<span class="pipeline-summary-label">Started</span>'
            f'<span class="pipeline-summary-value">{tracker.start_time_str}</span>'
            f'</span>'
        )
        if tracker.end_time_str:
            summary_parts.append(
                f'<span class="pipeline-summary-item">'
                f'<span class="pipeline-summary-label">Ended</span>'
                f'<span class="pipeline-summary-value">{tracker.end_time_str}</span>'
                f'</span>'
            )
        summary_parts.append(
            f'<span class="pipeline-summary-item">'
            f'<span class="pipeline-summary-label">Total</span>'
            f'<span class="pipeline-summary-value">{tracker.global_elapsed_str}</span>'
            f'</span>'
        )
    summary_html = (
        f'<div class="pipeline-summary">{"".join(summary_parts)}</div>'
        if summary_parts
        else ""
    )

    steps_str = "".join(steps_html)
    return f'<div class="pipeline-timeline-wrapper"><div class="pipeline-timeline">{steps_str}</div>{summary_html}</div>'
