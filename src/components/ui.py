"""Shared Streamlit UI helpers used across tabs.

Kept dependency-free except for streamlit so any tab can import it safely.
"""

import base64
import streamlit as st

# Aspect ratio -> (width, height) pairs tuned for Flux.2 Klein 4b.
# Multiples of 64 keep the UNet happy. Defaults favour landscape 16:9.
ASPECT_DIMS = {
    "16:9": (1344, 768),
    "21:9": (1536, 640),
    "4:3": (1024, 768),
    "3:2": (1152, 768),
    "1:1": (1024, 1024),
    "9:16": (768, 1344),
    "2:3": (768, 1152),
}


def aspect_to_dims(aspect_ratio: str) -> tuple:
    """Return a (width, height) tuple for an aspect ratio string."""
    return ASPECT_DIMS.get(aspect_ratio, (1344, 768))


def video_dims_for(aspect_ratio: str) -> tuple:
    """Wan 2.2 friendly resolutions (smaller than image dims)."""
    if aspect_ratio in ("9:16", "2:3"):
        return (480, 832)
    return (832, 480)


def copy_button(text: str, label: str = "Copy", key: str | None = None, small: bool = True) -> None:
    """Render a one-click copy-to-clipboard button next to a prompt block.

    Uses ``streamlit.components.v1.html`` so the ``<script>`` tag survives
    Streamlit's sanitizer (``st.markdown`` strips scripts).
    """
    import uuid
    try:
        from streamlit.components.v1 import html as stc_html
    except ImportError:
        from streamlit.components.v1 import components as stc_mod
        stc_html = stc_mod.html

    uid = (key or "cp") + "-" + uuid.uuid4().hex[:8]
    btn_classes = "sw-copy-btn" + (" sw-copy-btn-sm" if small else "")
    payload = base64.b64encode(text.encode("utf-8")).decode("ascii")

    stc_html(
        f"""
        <button id="{uid}" type="button" class="{btn_classes}"
                aria-label="Copy {label} to clipboard">📋 {label}</button>
        <span id="{uid}-msg" class="sw-copy-msg"></span>
        <script>
            (function() {{
                var btn = document.getElementById("{uid}");
                if (!btn || btn.dataset.bound) return;
                btn.dataset.bound = "1";
                btn.addEventListener("click", function() {{
                    var b64 = "{payload}";
                    var text = decodeURIComponent(escape(atob(b64)));
                    var msg = document.getElementById("{uid}-msg");
                    var done = function() {{
                        msg.textContent = "✓ copied";
                        setTimeout(function() {{ msg.textContent = ""; }}, 1500);
                    }};
                    if (navigator.clipboard && navigator.clipboard.writeText) {{
                        navigator.clipboard.writeText(text).then(done).catch(function() {{
                            var ta = document.createElement("textarea");
                            ta.value = text; document.body.appendChild(ta);
                            ta.select(); try {{ document.execCommand("copy"); done(); }}
                            catch(e) {{ msg.textContent = "press ⌘C"; }}
                            document.body.removeChild(ta);
                        }});
                    }} else {{
                        var ta = document.createElement("textarea");
                        ta.value = text; document.body.appendChild(ta);
                        ta.select(); try {{ document.execCommand("copy"); done(); }}
                        catch(e) {{ msg.textContent = "press ⌘C"; }}
                        document.body.removeChild(ta);
                    }}
                }});
            }})();
        </script>
        """,
        height=40,
    )


# Styles for the copy buttons + clipboard affordances. Injected once at app boot
# via inject_ui_assets() so we don't repeat it on every call.
_COPY_CSS = """
<style>
    .sw-copy-btn {
        font-family: 'Inter', sans-serif;
        font-size: 0.8rem;
        font-weight: 500;
        padding: 0.25em 0.7em;
        border-radius: 0.375rem;
        border: 1px solid var(--olive-400, #a7ae8b);
        background: var(--olive-100, #f5f5f4);
        color: var(--olive-900, #1f2117);
        cursor: pointer;
        margin: 0.2em 0;
        transition: background-color 0.15s ease;
    }
    .sw-copy-btn:hover { background: var(--olive-200, #e7e5e4); }
    .sw-copy-btn-sm { font-size: 0.72rem; padding: 0.15em 0.55em; }
    .sw-copy-msg {
        font-family: 'Inter', sans-serif;
        font-size: 0.75rem;
        color: var(--green, oklch(52% 0.090 145));
        margin-left: 0.5em;
    }
</style>
"""


def inject_ui_assets() -> None:
    """Inject the one-time CSS assets used by the UI helpers."""
    st.markdown(_COPY_CSS, unsafe_allow_html=True)


def connection_badge(ok: bool, label_ok: str = "Connected", label_bad: str = "Offline") -> str:
    """Return HTML for a small connection pill. Caller renders via st.markdown."""
    cls = "conn-ok" if ok else "conn-bad"
    text = label_ok if ok else label_bad
    return f'<span class="conn-badge {cls}">{text}</span>'


def prompt_block(title: str, text: str, key: str | None = None) -> None:
    """Render a labelled prompt block with a copy button + code view."""
    col_btn, col_spacer = st.columns([1, 6])
    with col_btn:
        copy_button(text, label="Copy", key=key)
    st.caption(f"**{title}**")
    st.code(text, language="text")
