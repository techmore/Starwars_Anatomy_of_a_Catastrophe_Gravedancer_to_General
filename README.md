# Gravedancer to General: Anatomy of a Catastrophe

A local Streamlit web application for creating and managing episodes of a Star Wars fan series chronicling Qymaen jai Sheelal's evolution into General Grievous. Generate stories with **Ollama**, then create visual pipelines for **DrawThings** (Flux.2 Klein 4b images + Wan 2.2 High Noise 6-bit SVDQuant video).

## Features

- **Episode Creator**: Generate multi-day stories (3-8 days) with structured input
- **Story Viewer/Editor**: Review, edit, and parse generated stories
- **Scene Prompts**: Auto-extract key scenes and generate image/video prompts
- **Episode Library**: Manage and export your entire series
- **DrawThings Integration**: Optimized prompts for Flux.2 Klein 4b and Wan 2.2

## Setup

### Prerequisites

1. **Python 3.9+**
2. **Ollama** running locally ([install](https://ollama.com/))
3. **DrawThings** app for image/video generation

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

### Pull an Ollama Model

**Default: `qwen3.6:27b` (recommended for 7,500-word novellas):**
```bash
ollama pull qwen3.6:27b       # ~18-20GB RAM — excellent prose + structure following
```

**Other top-tier options:**
```bash
ollama pull qwen2.5:32b       # ~20GB RAM — excellent prose, long context
ollama pull llama3.1:70b      # ~40GB RAM — best in class
ollama pull gemma2:27b        # ~16GB RAM — Google, strong instruction-following
ollama pull command-r         # ~20GB RAM — Cohere, creative-tuned
```

**Faster / lighter (still good):**
```bash
ollama pull llama3.1          # ~4.7GB — solid default
ollama pull gemma2            # ~5.4GB — fast, good prose
ollama pull mixtral           # ~26GB — MoE, strong creative
```

The app defaults to `qwen3.6:27b` and auto-detects installed models. Models are sorted by story-friendliness and labeled with quality indicators (★ best, ● good, ○ ok). The sidebar picks the best available model for you.

### Start Ollama

```bash
ollama serve
```

### Run the App

```bash
streamlit run app.py
```

The app will open at `http://localhost:8501`.

## Workflow

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
   - Generate DrawThings + Flux.2 Klein 4b image prompts (5 variations per scene)
   - Generate Wan 2.2 High Noise 6-bit SVDQuant video prompts
   - Export as JSON or TXT

4. **Manage Library** (Tab 4)
   - Browse all episodes
   - Export as Markdown, JSON, or prompts bundle

## DrawThings Workflow

### Image Generation (Flux.2 Klein 4b)

1. Open **DrawThings**
2. Load model: **Flux.2 Klein 4b**
3. Set aspect ratio (16:9 = 1344x768 recommended)
4. Settings:
   - Steps: 20-30
   - CFG Scale: 2.0-3.0
   - Sampler: Euler a
5. Paste prompt from app
6. Generate and save keyframe

### Video Generation (Wan 2.2 High Noise 6-bit SVDQuant)

1. Load **Wan 2.2 High Noise 6-bit SVDQuant** I2V model in DrawThings
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
│   ├── components/        # Streamlit tab components
│   ├── prompts/           # System prompts
│   └── utils/             # Ollama client, storage, generators
├── app.py                 # Main Streamlit app
├── requirements.txt
└── README.md
```

## Configuration

All settings are in the sidebar:
- **Ollama URL**: Default `http://localhost:11434`
- **Model**: Select from installed Ollama models
- **Temperature**: Creativity slider (0.0-2.0)
- **Storage Path**: Where episodes are saved
- **System Prompts**: Edit the story generation and visual prompt system prompts

## Tech Stack

- **Streamlit**: Web UI framework
- **Ollama**: Local LLM inference
- **DrawThings**: Image/video generation (external)
- **Flux.2 Klein 4b**: Image generation model
- **Wan 2.2 High Noise 6-bit SVDQuant**: Image-to-video model
- **Python**: requests, pillow, pyyaml

## Notes

- All processing is local and private
- Stories are saved as Markdown + JSON
- Episode data is stored in `episodes/` folder
- You can edit system prompts in the sidebar for fine-tuning
- The app supports streaming generation for long stories

## License

Fan project — Star Wars is © Lucasfilm/Disney. This is a non-commercial creative tool.
