"""Main prototype UI entrypoint for Gravedancer to General."""

import streamlit as st

from src.components.sidebar import render_sidebar
from src.components.tab_story import render_story_stage
from src.components.tab_art import render_art_stage
from src.components.tab_prompts import render_prompts_tab
from src.components.tab_viewer import render_viewer_tab
from src.components.tab_library import render_library_tab
from src.components.theme import CUSTOM_CSS
from src.utils.prompt_generator import PromptGenerator
from src.utils.app_context import AppContext
from src.utils.session_state import init_session_state
from src.utils.story_generator import StoryGenerator

def main():
    st.set_page_config(
        page_title="Gravedancer to General",
        page_icon="⚔️",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    init_session_state(st)

    ollama, dt_client, model, temperature, storage = render_sidebar()
    context = AppContext(
        ollama=ollama,
        dt_client=dt_client,
        model=model,
        temperature=temperature,
        storage=storage,
        story_gen=StoryGenerator(ollama),
        prompt_gen=PromptGenerator(ollama),
    )

    st.markdown("# Gravedancer to General")
    st.markdown("*Anatomy of a Catastrophe - A Star Wars fan series*")
    st.markdown("---")

    tab_story, tab_art, tab_prompts, tab_viewer, tab_library = st.tabs(
        ["📖 Story", "🎨 Art", "🧩 Prompts", "👁 Viewer", "📚 Library"]
    )

    with tab_story:
        render_story_stage(context)

    with tab_art:
        render_art_stage(context)

    with tab_prompts:
        render_prompts_tab(
            context=context,
            ollama_url=st.session_state["ollama_url"],
            visual_system_prompt=st.session_state["visual_sys_prompt"],
        )

    with tab_viewer:
        render_viewer_tab(context)

    with tab_library:
        render_library_tab(context)


if __name__ == "__main__":
    main()
