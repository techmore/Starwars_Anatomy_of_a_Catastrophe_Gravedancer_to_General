"""Sidebar: MLX + Draw Things configuration, library, advanced settings."""

import streamlit as st

from src.utils.logging_utils import get_logger, get_run_log_name, list_log_runs, read_log_tail, start_new_run_log
from src.utils.mlx_client import get_mlx_client, OPENCODE_PREFIX, OPENCODE_DEFAULT_MODEL
from src.utils.models import get_m1_pro_32gb_guidance, normalize_model_name, list_local_mlx_models, DEFAULT_MODEL
from src.utils.storage import get_storage
from src.utils.drawthings_client import get_drawthings_client, DEFAULT_DT_PORTS
from src.utils.session_state import episode_selector_label


LOGGER = get_logger(__name__)


@st.cache_resource
def _get_cached_mlx_client(model_name: str):
    """Cache MLX clients at the UI composition boundary."""
    return get_mlx_client(model_name)


@st.cache_resource
def _get_cached_drawthings_client(base_url: str):
    """Cache Draw Things clients at the UI composition boundary."""
    return get_drawthings_client(base_url)


@st.cache_resource
def _get_cached_storage(base_path: str):
    """Cache lightweight storage handles for Streamlit reruns."""
    return get_storage(base_path)


def _cached_mlx_status(model_name: str):
    cache_key = f"mlx_status:{model_name}"
    cached = st.session_state.get(cache_key)
    if cached is None:
        cached = {
            "connected": _get_cached_mlx_client(model_name).check_connection(),
            "model_available": _get_cached_mlx_client(model_name).is_model_available_locally(model_name),
            "model_supported": _get_cached_mlx_client(model_name).is_model_supported_by_runtime(model_name),
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
                probe = _get_cached_drawthings_client(f"http://localhost:{port}")
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

        # ---------- Text generation ----------
        current_backend_model = str(st.session_state["mlx_model"])
        backend_label = "OpenCode" if current_backend_model.startswith(OPENCODE_PREFIX) else ("LM Studio" if current_backend_model.startswith("lmstudio:") else "MLX")
        st.markdown(f"**Text generation · {backend_label}**")
        local_models = list_local_mlx_models()
        model_options = [("OpenCode / Zen · DeepSeek V4 Free", f"{OPENCODE_PREFIX}{OPENCODE_DEFAULT_MODEL}")] + local_models + [("Custom...", "__custom__")]
        current_model = st.session_state["mlx_model"]
        # Find current model in options; default to Custom if not found
        local_repo_ids = [r for _, r in local_models]
        current_idx = len(model_options) - 1  # default to Custom
        for idx, (label, repo_id) in enumerate(model_options):
            if repo_id == current_model:
                current_idx = idx
                break
        selected = st.selectbox(
            "Model",
            options=model_options,
            format_func=lambda x: x[0],
            index=current_idx,
            key="model_selector",
            label_visibility="collapsed",
        )
        if selected[1] == "__custom__":
            model = st.text_input(
                "Custom model",
                value=current_model,
                key="custom_model_input",
                label_visibility="collapsed",
                help="Enter a Hugging Face repo ID or local path.",
            )
        else:
            model = selected[1]
        model = normalize_model_name(model)
        if model != current_model:
            # Release the previous client's model weights before the new
            # resource is used. This matters on the 32 GB unified-memory
            # target, especially after testing a 27B/32B model.
            _get_cached_mlx_client(current_model).release_loaded_model()
        st.session_state["mlx_model"] = model
        mlx = _get_cached_mlx_client(model)
        if str(model).startswith(OPENCODE_PREFIX):
            st.markdown('<span class="conn-badge conn-ok">✓ OpenCode selected</span>', unsafe_allow_html=True)
            st.caption("Generation will run through the local `opencode` CLI using the configured provider/model.")
            lm_status = None
            mlx_status = {"connected": True, "model_available": True, "model_supported": True}
        elif str(model).startswith("lmstudio:"):
            lm_status = mlx.check_lmstudio(model)
            if not lm_status["available"]:
                st.markdown('<span class="conn-badge conn-bad">✗ LM Studio offline</span>', unsafe_allow_html=True)
                st.caption("Start LM Studio’s local server before generating. Expected endpoint: `http://127.0.0.1:1234`.")
            elif not lm_status["model_loaded"]:
                st.markdown('<span class="conn-badge conn-bad">✗ Model not loaded</span>', unsafe_allow_html=True)
                st.caption(f"Load `{model.removeprefix('lmstudio:')}` in LM Studio, then retry.")
            else:
                st.markdown('<span class="conn-badge conn-ok">✓ LM Studio ready</span>', unsafe_allow_html=True)
                st.caption("LM Studio local server and selected model are ready.")
        else:
            lm_status = None
        LOGGER.info("sidebar model resolved model=%s session_model=%s", model, st.session_state["mlx_model"])

        if str(model).startswith(OPENCODE_PREFIX):
            mlx_status = {"connected": True, "model_available": True, "model_supported": True}
        else:
            mlx_status = _cached_mlx_status(model) if lm_status is None else {"connected": True, "model_available": True, "model_supported": True}
        if lm_status is None and mlx_status["connected"] and mlx_status["model_available"] and mlx_status["model_supported"]:
            st.markdown('<span class="conn-badge conn-ok">✓ Ready</span>', unsafe_allow_html=True)
            st.caption("MLX is available and ready to generate text.")
        elif mlx_status["connected"] and mlx_status["model_available"]:
            st.markdown('<span class="conn-badge conn-bad">✗ Model runtime unsupported</span>', unsafe_allow_html=True)
            st.caption("This model is downloaded, but the active MLX runtime cannot run its weight format. Bonsai 1-bit requires Prism's MLX fork in an isolated runtime.")
        elif mlx_status["connected"]:
            st.markdown('<span class="conn-badge conn-bad">✗ Model unavailable locally</span>', unsafe_allow_html=True)
            st.caption("The MLX runtime is available, but this model is not installed locally. Choose a cached model or prepare it before running offline.")
        else:
            st.markdown('<span class="conn-badge conn-bad">✗ MLX unavailable</span>', unsafe_allow_html=True)
            st.caption("Install `mlx_lm` and confirm the model path is available locally.")
            model = st.session_state.get("mlx_model", "")

        guidance = get_m1_pro_32gb_guidance(model)
        st.caption(f"**M1 Pro 32 GB:** {guidance['label']} — {guidance['detail']}")
        st.caption(guidance["concurrency"])

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

        dt_client = _get_cached_drawthings_client(dt_url)
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
        storage = _get_cached_storage(storage_path)
        LOGGER.info("sidebar storage path=%s episodes=%s", storage_path, len(storage.list_episodes()))

        st.markdown("---")

        # ---------- Library (compact) ----------
        st.markdown("**Library**")
        episodes = storage.list_episodes()
        if episodes:
            for ep in episodes[:5]:
                cols = st.columns([3, 1])
                with cols[0]:
                    viewing = st.session_state.get("viewer_selected_id")
                    if viewing == ep["id"]:
                        st.markdown(f"**{ep['title'][:35]}{'…' if len(ep['title']) > 35 else ''}**")
                    else:
                        st.markdown(f"_{ep['title'][:35]}{'…' if len(ep['title']) > 35 else ''}_")
                with cols[1]:
                    if st.button("Open", key=f"side_view_{ep['id']}", help="Open episode in main pane"):
                        st.session_state["viewer_selected_id"] = ep["id"]
                        st.rerun()
            st.caption("Open an episode in Review workspace")
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

            st.markdown("---")
            st.markdown("**Current Run**")
            st.caption(get_run_log_name())
            if st.button("Start New Run Bucket", key="sidebar_new_run", use_container_width=True):
                st.session_state["log_run_path"] = str(start_new_run_log("manual"))
                st.rerun()

            st.markdown("---")
            st.markdown("**Log Tail**")
            max_lines = st.slider("Lines", min_value=20, max_value=300, value=120, step=10, key="log_tail_lines")
            tail = read_log_tail(max_lines=max_lines)
            if tail:
                st.code(tail, language="text")
            else:
                st.caption("No log entries yet.")

            st.markdown("---")
            st.markdown("**Recent Runs**")
            runs = list_log_runs(limit=5)
            if runs:
                for run in runs:
                    st.caption(run.name)
            else:
                st.caption("No archived run logs yet.")

    return mlx, dt_client, st.session_state["mlx_model"], st.session_state["temperature"], storage


def _try_switch(dt_client, hint: str) -> None:
    """Attempt to switch the active Draw Things model by name hint."""
    try:
        dt_client.switch_model(hint)
        st.toast(f"Switched Draw Things model toward '{hint}'")
        st.rerun()
    except Exception as e:
        st.error(f"Couldn't switch model: {e}")
