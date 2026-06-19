# Gravedancer to General: Anatomy of a Catastrophe

A local, Mac-first creator console for building episodes of a Star Wars fan series chronicling Qymaen jai Sheelal's evolution into General Grievous. Generate stories with **MLX** on Apple Silicon, then build visual workflows for **Draw Things** using **Flux.2 Klein 4b** for stills and **Wan 2.2 High Noise 6-bit SVDQuant** for video prep.

## Features

- **Episode Creator**: Generate multi-day stories (3-8 days) with structured input
- **Story Viewer/Editor**: Review, edit, and parse generated stories
- **Scene Prompts**: Auto-extract key scenes and generate image/video prompts
- **Episode Library**: Manage and export your entire series
- **Draw Things Integration**: Optimized prompts for Flux.2 Klein 4b and Wan 2.2
- **Local-first workflow**: Works offline after MLX and Draw Things are available
- **Mac-first UI direction**: Streamlit is the current prototype shell, not a commitment to the final UI

## Setup

### Prerequisites

1. **Python 3.9+**
2. **MLX** Python runtime with `mlx_lm`
3. **Draw Things** app for image/video generation on macOS

### Installation

```bash
# Clone or navigate to the project
cd gravedancer-to-general

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Prepare the MLX Model

**Default: `mlx-community/Qwen3.6-27B-4bit` (lighter Apple Silicon option):**
```bash
python -m mlx_lm.generate --model mlx-community/Qwen3.6-27B-4bit --prompt "Sanity check"
```

**Other top-tier options:**
```bash
python -m mlx_lm.generate --model mlx-community/Qwen3.6-27B-4bit --prompt "Your creative writing prompt here"
```

**Faster / lighter (still good):**
```bash
python -m mlx_lm.generate --model mlx-community/Qwen3.6-8B-4bit --prompt "Your creative writing prompt here"
```

The app defaults to `mlx-community/Qwen3.6-27B-4bit` and lets you edit the model path directly in the sidebar.

### Run the Prototype Shell

```bash
streamlit run app.py
```

This opens the current Streamlit prototype shell at `http://localhost:8501`.
The core story, prompt, storage, and Draw Things modules are kept reusable so the presentation layer can be swapped later if a more Mac-native UI becomes the better fit.

## Workflow

The app is organized as a modular prototype UI shell with separate tabs for story, art, prompts, viewer, and library.

1. **Create Episode** (Tab 1)
   - Enter title, number of days, Jedi details, setting, tone
   - Click "Generate Story"
   - Save to library

2. **Review/Edit** (Tab 2)
   - Load saved episode
   - Review days, edit prose
   - View stats (word count, reading time)

3. **Generate Visual Prompts** (Tab 3)
   - Extract key scenes from story
   - Generate Draw Things + Flux.2 Klein 4b image prompts
   - Generate Wan 2.2 High Noise 6-bit SVDQuant video prompts
   - Export as JSON or TXT

4. **Manage Library** (Tab 4)
   - Browse all episodes
   - Export as Markdown, JSON, or prompts bundle

## Draw Things Workflow

### Image Generation (Flux.2 Klein 4b)

1. Open **Draw Things**
2. Load model: **Flux.2 Klein 4b**
3. Set aspect ratio (16:9 = 1344x768 recommended)
4. Settings:
   - Steps: 20-30
   - CFG Scale: 2.0-3.0
   - Sampler: Euler a
5. Paste prompt from app
6. Generate and save keyframe

### Video Generation (Wan 2.2 High Noise 6-bit SVDQuant)

1. Load **Wan 2.2 High Noise 6-bit SVDQuant** I2V model in Draw Things
2. Input: keyframe image from Flux.2 Klein 4b
3. Paste Wan 2.2 motion prompt
4. Settings:
   - Resolution: 480x832 or 832x480
   - FPS: 24
   - Steps: 25
   - CFG: 7.0
   - Motion Bucket: 127 (adjust 1-255)
5. Generate 3-5 second clip

## Folder Structure

```
gravedancer-to-general/
├── episodes/              # Saved episodes (auto-created)
│   ├── episode-XXX/
│   │   ├── metadata.json
│   │   ├── story.md
│   │   └── prompts.json
├── images/                # Generated images (create manually)
├── videos/                # Generated videos (create manually)
├── src/                   # Source code
│   ├── components/        # UI components and tabs
│   ├── prompts/           # System prompts
│   └── utils/             # MLX client, storage, generators, Draw Things client
├── app.py                 # Main prototype UI entrypoint
├── requirements.txt
└── README.md
```

## Configuration

All settings are in the sidebar:
- **MLX Model**: Set the local MLX model path or repo ID
- **Temperature**: Creativity slider (0.0-2.0)
- **Storage Path**: Where episodes are saved
- **System Prompts**: Edit the story generation and visual prompt system prompts

## Tech Stack

- **Streamlit**: Current prototype UI shell only
- **MLX / mlx_lm**: Local LLM inference on Apple Silicon
- **Draw Things**: Image/video generation (external)
- **Flux.2 Klein 4b**: Image generation model
- **Wan 2.2 High Noise 6-bit SVDQuant**: Image-to-video model
- **Python**: requests, streamlit

## Notes

- All processing is local and private
- Stories are saved as Markdown + JSON
- Episode data is stored in `episodes/` folder
- You can edit system prompts in the sidebar for fine-tuning
- The app supports streaming generation for long stories
- The current implementation is modular under `src/components/` and `src/utils/`
- The UI is intentionally kept thin so the rendering layer can be replaced later if a more Mac-native shell becomes the better fit
- The intended visual workflow is MLX -> Draw Things, not ComfyUI

## Planning Docs

- [`prompt.md`](prompt.md) - product brief and hard requirements
- [`docs/INDEX.md`](docs/INDEX.md) - docs landing page
- [`docs/consistency-plan.md`](docs/consistency-plan.md) - current alignment checklist
- [`docs/mac-ui-architecture.md`](docs/mac-ui-architecture.md) - future UI boundaries
- [`docs/ui-migration-checklist.md`](docs/ui-migration-checklist.md) - shell swap phases
- [`docs/ui-migration-roadmap.md`](docs/ui-migration-roadmap.md) - implementation order
- [`docs/REQUIREMENTS-TRACE.md`](docs/REQUIREMENTS-TRACE.md) - prompt-to-implementation trace
- [`docs/PROJECT-STATUS.md`](docs/PROJECT-STATUS.md) - current handoff summary

## License

Fan project — Star Wars is © Lucasfilm/Disney. This is a non-commercial creative tool.
