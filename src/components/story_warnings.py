"""Streamlit rendering for story-quality validation reports."""

from typing import Any

import streamlit as st


def render_warnings(report: dict[str, Any]) -> None:
    """Render quality warnings as alert cards when validation found any."""
    warnings = report.get("warnings") or []
    if not warnings:
        return

    body = "\n".join(f"• {warning}" for warning in warnings)
    st.markdown(
        f'<div class="quality-warn"><strong>⚠️ Quality check</strong><br/>{body}</div>',
        unsafe_allow_html=True,
    )
