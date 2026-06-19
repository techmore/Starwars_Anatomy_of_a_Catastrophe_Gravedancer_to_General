"""Sidebar: MLX + Draw Things configuration, library, advanced settings."""

import streamlit as st

from src.utils.mlx_client import get_mlx_client
from src.utils.storage import get_storage
from src.utils.models import (
    get_model_info, sort_models_for_ui, get_recommended_default,
    format_model_label, get_install_commands,
)
from src.utils.concepts import get_used_jedi_names
from src.utils.drawthings_client import get_drawthings_client, DEFAULT_DT_PORTS


def _cached_mlx_status(model_name: str):
    cache_key = f"mlx_status:{model_name}"
    cached = st.session_state.get(cache_key)
    if cached is None:
        cached = {
            "connected": get_mlx_client(model_name).check_connection(),
            "models": [model_name],
        }
        st.session_state[cache_key] = cached
    return cached


def _cached_drawthings_status(dt_client, dt_url: str):
    cache_key = f"drawthings_status:{dt_url}"
    cached = st.session_state.get(cache_key)
    if cached is None:
        connected = dt_client.check_connection()
        if not connected and dt_url == f"http://localhost:{DEFAULT_DT_PORTS[0]}":
            for port in DEFAULT_DT_PORTS[1:]:
                probe = get_drawthings_client(f"http://localhost:{port}")
                if probe.check_connection():
                    dt_client = probe
                    dt_url = f"http://localhost:{port}"
                    connected = True
                    break
        cached = {
            "connected": connected,
            "dt_url": dt_url,
            "current_model": dt_client.current_model_name() if connected else "",
            "models": dt_client.list_models() if connected else [],
            "client": dt_client,
        }
        st.session_state[cache_key] = cached
    return cached


def render_sidebar():
    """Render the sidebar. Returns (mlx, dt_client, model, temperature, storage)."""
    with st.sidebar:
        st.markdown("## ⚙️ Settings")

        # ---------- MLX ----------
        st.markdown("**MLX**")
        model = st.text_input(
            "Model",
            value=st.session_state["model"],
            key="model_input",
            label_visibility="collapsed",
            help="Use a local MLX model path or Hugging Face repo ID, e.g. `mlx-community/Qwen3.6-27B-4bit`.",
        )
        st.session_state["model"] = model
        mlx = get_mlx_client(model)

        mlx_status = _cached_mlx_status(model)
        if mlx_status["connected"]:
            st.markdown('<span class="conn-badge conn-ok">✓ Ready</span>', unsafe_allow_html=True)
            info = get_model_info(model)
            with st.expander("Model info", expanded=False):
                st.caption(f"**Quality:** {info.get('quality', '?').title()}")
                st.caption(f"**RAM:** {info.get('ram_gb', '?')} GB")
                st.caption(f"**Strengths:** {', '.join(info.get('strengths', ['unknown']))}")
        else:
            st.markdown('<span class="conn-badge conn-bad">✗ MLX unavailable</span>', unsafe_allow_html=True)
            st.caption("Install `mlx_lm` and confirm the model path is available locally.")
            model = st.session_state.get("model", "")

        st.markdown("---")

        # ---------- Draw Things ----------
        st.markdown("**Draw Things**")
        dt_url = st.text_input(
            "Draw Things URL",
            value=st.session_state["drawthings_url"],
            key="drawthings_url_input",
            label_visibility="collapsed",
            help="Local Draw Things API server. Enable it in Draw Things → Settings → API Server.",
        )
        st.session_state["drawthings_url"] = dt_url

        dt_client = get_drawthings_client(dt_url)
        dt_status = _cached_drawthings_status(dt_client, dt_url)
        dt_ok = dt_status["connected"]
        dt_client = dt_status["client"]
        st.session_state["drawthings_url"] = dt_status["dt_url"]
        if dt_ok:
            st.markdown('<span class="conn-badge conn-ok">✓ Connected</span>', unsafe_allow_html=True)
            current_model = dt_status["current_model"]
            if current_model:
                st.caption(f"Active model: **{current_model}**")
            # Model quick-switch buttons (filled out in Phase 3 integration).
            dt_models = dt_status["models"]
            if dt_models:
                sw_col1, sw_col2 = st.columns(2)
                with sw_col1:
                    if st.button("Flux.2 Klein 4b", key="dt_switch_flux", use_container_width=True, help="Switch to Flux.2 Klein 4b for keyframes"):
                        _try_switch(dt_client, "Flux.2 Klein 4b")
                with sw_col2:
                    if st.button("Wan 2.2", key="dt_switch_wan", use_container_width=True, help="Switch to Wan 2.2 for image-to-video"):
                        _try_switch(dt_client, "Wan 2.2")
        else:
            st.markdown('<span class="conn-badge conn-bad">✗ Offline</span>', unsafe_allow_html=True)
            with st.expander("How to enable", expanded=False):
                st.markdown(
                    "1. Open **Draw Things → Settings (⌘,)**\n"
                    "2. Find **API Server** (under Advanced)\n"
                    "3. Enable it and note the port\n"
                    "4. Put the full URL above, e.g. `http://localhost:7860`"
                )

        st.markdown("---")

        # ---------- Creativity ----------
        st.markdown("**Creativity**")
        temperature = st.slider(
            "Temperature",
            min_value=0.0,
            max_value=2.0,
            value=st.session_state["temperature"],
            step=0.1,
            key="temp_slider",
            label_visibility="collapsed",
        )
        st.session_state["temperature"] = temperature

        st.markdown("---")

        # ---------- Storage ----------
        st.markdown("**Storage**")
        storage_path = st.text_input(
            "Episodes folder",
            value=st.session_state["storage_path"],
            key="storage_path_input",
            label_visibility="collapsed",
        )
        st.session_state["storage_path"] = storage_path
        storage = get_storage(storage_path)

        st.markdown("---")

        # ---------- Library (compact) ----------
        st.markdown("**Library**")
        episodes = storage.list_episodes()
        if episodes:
            for ep in episodes[:5]:
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.markdown(f"_{ep['title'][:25]}_")
                with col2:
                    # Two-step delete: expand a confirm instead of instant wipe.
                    if st.button("×", key=f"side_del_{ep['id']}", help="Delete episode"):
                        st.session_state[f"confirm_del_{ep['id']}"] = True
                        st.rerun()
                    if st.session_state.get(f"confirm_del_{ep['id']}"):
                        st.warning("Delete?", icon="⚠️")
                        c1, c2 = st.columns(2)
                        with c1:
                            if st.button("Yes", key=f"side_del_yes_{ep['id']}", type="primary"):
                                storage.delete_episode(ep["id"])
                                st.session_state.pop(f"confirm_del_{ep['id']}", None)
                                st.rerun()
                        with c2:
                            if st.button("No", key=f"side_del_no_{ep['id']}"):
                                st.session_state.pop(f"confirm_del_{ep['id']}", None)
                                st.rerun()
        else:
            st.markdown("_No episodes yet_")

        st.markdown("---")

        # ---------- Advanced ----------
        with st.expander("Advanced", expanded=False):
            st.markdown("**System Prompts**")
            story_sys = st.text_area(
                "Story prompt",
                value=st.session_state["story_sys_prompt"],
                height=200,
                key="story_sys_editor",
            )
            st.session_state["story_sys_prompt"] = story_sys

            visual_sys = st.text_area(
                "Visual prompt",
                value=st.session_state["visual_sys_prompt"],
                height=200,
                key="visual_sys_editor",
            )
            st.session_state["visual_sys_prompt"] = visual_sys

    return mlx, dt_client, st.session_state["model"], st.session_state["temperature"], storage


def _try_switch(dt_client, hint: str) -> None:
    """Attempt to switch the active Draw Things model by name hint."""
    try:
        dt_client.switch_model(hint)
        st.toast(f"Switched Draw Things model toward '{hint}'")
        st.rerun()
    except Exception as e:
        st.error(f"Couldn't switch model: {e}")
