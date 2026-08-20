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

1. **Python 3.10+** (the isolated Bonsai runtime uses Python 3.11)
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

For repository verification, run:

```bash
pytest -q
python3 -m compileall -q app.py run_creative_pipeline.py scripts src tests
```

### Prepare the MLX Model

**Primary: `mlx-community/Qwen3.8-27B-OptiQ-4bit` (Qwen 3.8 27B, ~15–20GB):**
```bash
# Installed by the app's isolated Bonsai runtime, not the primary environment.
~/.local/share/gravedancer/bonsai-runtime/bin/python -c 'import mlx.core as mx; mx.quantize(mx.zeros((1, 128)), group_size=128, bits=1); print("Bonsai runtime ready")'
```

**Higher-quality option for Macs with sufficient unified memory:**
```bash
python3 -m mlx_lm.generate --model mlx-community/Qwen3-32B-4bit --prompt "Your creative writing prompt here"
```

**Faster / lighter (still good):**
```bash
python3 -m mlx_lm.generate --model mlx-community/Qwen3-8B-4bit --prompt "Your creative writing prompt here"
```

The app defaults to `mlx-community/Qwen3.8-27B-OptiQ-4bit` for the highest-quality local story work. Gemma 4 E4B IT OptiQ is the fast-story fallback, and Gemma 4 E2B IT is the utility model. Bonsai remains supported through its isolated runtime when installed.

To prepare that isolated runtime without modifying the app environment, run:

```bash
sh scripts/setup_bonsai_runtime.sh --download-model
```

Omit `--download-model` when Bonsai is already in the local Hugging Face cache.

### M1 Pro with 32 GB unified memory

- Use Qwen 3.8 27B OptiQ for the best local story and editorial passes on the 32 GB M1 Pro. Keep individual generation passes and context bounded.
- Pause large Draw Things renders while generating a long story section; normal prompt work can coexist.
- Use Gemma 4 E4B IT OptiQ for routine drafting and Qwen 3.5 4B or Gemma 4 E2B IT for quick structured iteration.
- Treat conventional 27B and 32B 4-bit models as **single-workload** story sessions: close Draw Things, avoid switching models during a run, and generate a day or chapter at a time.
- The app releases the previous MLX model when you switch models and uses bounded multi-pass output ceilings to reduce unified-memory pressure.
- Model loading is offline by default. To intentionally let MLX download or update a model, start the app with `GRAVEDANCER_ALLOW_MODEL_DOWNLOADS=1`.
- LM Studio models can be selected through the custom model field with the `lmstudio:` prefix, for example `lmstudio:your-model-id`. LM Studio generation streams through its local OpenAI-compatible API. The default output ceiling is 8192 tokens; override it with `GRAVEDANCER_LMSTUDIO_MAX_TOKENS` when a model or workload needs a different bound.

### Run the Prototype Shell

```bash
streamlit run app.py
```

This opens the current Streamlit prototype shell at `http://localhost:8501`.
The core story, prompt, storage, and Draw Things modules are kept reusable so the presentation layer can be swapped later if a more Mac-native UI becomes the better fit.

### Terminal UI (Textual)

A cross-platform (macOS + Linux) TUI that makes harness and model selection explicit, drives **multiple pipeline runs side by side**, and streams every run's output live:

```bash
python tui.py
```

- **1 · Harness** — pick the backend: `rapid-mlx`, `LM Studio`, `Ollama`, a **remote OpenAI-compatible endpoint** (e.g. an Ubuntu box running Ollama/vLLM), **OpenCode** (hosted models via the `opencode` CLI, including the **ox-alpha Free** preset — no local VRAM needed), or **native MLX** (in-process). Harnesses are filtered by platform (MLX/rapid-mlx are Apple-only; LM Studio lists on macOS + Windows; Linux lists Ollama, OpenCode, and remote endpoints).
- **2 · Model** — browsed live from the harness (`GET /v1/models` for HTTP backends, local MLX cache for native mode).
- **3 · Seed** — the creative seed, shared by every run you launch.
- **4 · Remote target (SSH)** — point at an Ubuntu box by IP:
  - **Test SSH** probes connectivity (key-based auth via `~/.ssh/config`/ssh-agent, `BatchMode` so it never prompts), then reports python3 / venv / Ollama presence and lists the models the box is serving.
  - **Deploy** `rsync`s the project over SSH (excluding venv/log/episodes/Images/.models), creates a `venv` on the host if missing ("install if missing"), and refreshes the remote model list.
- **Run Local / Run Remote / Stop** — launch any number of runs concurrently (local on this machine, remote over SSH). Every run is a row in the **Runs (live)** panel showing status + elapsed time; select a run to inspect its streaming log. **Stop** halts the selected run — `SIGTERM` to the local process group, or terminate the ssh client plus a remote `pkill` for remote runs.

Keyboard: `Ctrl+Enter` run local · `X` stop selected · `R` refresh local models · `V` episode library · `O` open last finished episode · `Q` quit.

The **ox-alpha Free** preset routes to a hosted OpenCode model (default
`opencode/x-preview-f-free`; override with `GRAVEDANCER_OXALPHA_MODEL`). Note
that the OpenCode CLI path ignores temperature/top_p/max_tokens — output length
is bounded by the provider, not the app.

Because every HTTP harness speaks OpenAI-compatible chat completions, the same run works against rapid-mlx on this Mac or an Ubuntu box serving the same model via Ollama — either point the "Remote OpenAI endpoint" harness at that host (client runs locally), or use a **Remote target** (the whole pipeline runs on the box via SSH).

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
│   │   ├── prompts.json          # Created after prompt generation
│   │   └── images/               # Draw Things keyframes
├── src/                   # Source code
│   ├── components/        # UI components and tabs
│   ├── prompts/           # System prompts
│   └── utils/             # MLX client, storage, generators, SSH remoter, Draw Things client
├── scripts/               # Spec pilot, benchmark, and in-session pipeline runners
├── tests/                 # Pytest suite
├── docs/                  # Planning and status docs
├── app.py                 # Streamlit prototype UI entrypoint
├── tui.py                 # Textual terminal UI (multi-run pipeline driver)
├── run_creative_pipeline.py  # Structured seed → episode pipeline (used by TUI/SSH)
├── requirements.txt
└── README.md
```

## Configuration

All settings are in the sidebar:
- **MLX Model**: Set the local MLX model path or repo ID
- **Temperature**: Creativity slider (0.0-2.0)
- **Storage Path**: Where episodes are saved
- **System Prompts**: Edit the story generation and visual prompt system prompts

### Long-Form Runs and Recovery

Use the **Smoke test** profile first to verify LM Studio connectivity and the
episode save path. Use **Long-form** for the production workflow targeting
roughly 45,000 output tokens per day. Long runs display elapsed time, output
volume, and approximate throughput in the live monitor.

Completed days are checkpointed atomically under `.checkpoints/` in the active
storage directory. If generation fails, the Story tab offers **Resume from
checkpoint**; completed days are reused without another model call. Checkpoint
metadata includes the outline and creative inputs. After a successful episode
save, its checkpoint is removed automatically. Checkpoints are local runtime
artifacts and are excluded from Git by `.gitignore`.

Checkpointing works from every entrypoint: the Streamlit Story tab, the TUI
(local and remote runs), and `run_creative_pipeline.py` directly. Stopping a
TUI run (or sending SIGTERM to the pipeline) preserves all completed days;
rerun with the same `--seed` to resume.

To cooperatively stop a long run between model requests instead, set a sentinel
path before launching the app and create that file when you want generation to
stop:

```bash
export GRAVEDANCER_CANCEL_FILE="/tmp/gravedancer-cancel"
touch "$GRAVEDANCER_CANCEL_FILE"
```

The current model request is allowed to finish; cancellation occurs before the
next day or section and preserves the latest checkpoint. Remove the sentinel
before starting a new run.

Shared entrypoint settings can also be supplied through environment variables:

```bash
export GRAVEDANCER_MODEL="lmstudio:your-model-id"
export GRAVEDANCER_STORAGE_PATH="/path/to/episodes"
export GRAVEDANCER_LOG_PATH="/path/to/log"
```

The pilot workflow accepts the model and storage path explicitly:

```bash
python3 scripts/run_spec_pilot.py \
  --model "lmstudio:your-model-id" \
  --storage-path "/path/to/benchmark-episodes"
```

It also supports `--resume-episode <id>` to continue an interrupted pilot run
and `--finalize-episode <id>` to re-run validation/export on a saved episode.
`benchmark_model.py` additionally accepts `--prompt` (custom prompt text) and
`--output` (write the JSON report to a file).

For a bounded model-speed comparison that does not create an episode:

```bash
python3 scripts/benchmark_model.py \
  --model "lmstudio:ornith-1.5-9b-mlx" \
  --max-tokens 256
```

The report includes first-token latency, total latency, approximate tokens per
second, and output size. Use the same prompt and token limit when comparing
LM Studio models.

The Ornith 1.5 9B LM Studio benchmark measured approximately 8.8 output
tokens/second in one local run. At that rate, 45,000 output tokens is roughly
85 minutes of raw generation before prompt, checkpoint, and validation
overhead. Treat this as a planning estimate, not a guarantee; run the bounded
benchmark on the active machine before committing to a full episode.

## Tech Stack

- **Streamlit**: Current prototype UI shell only
- **MLX / mlx_lm**: Local LLM inference on Apple Silicon
- **Draw Things**: Image/video generation (external)
- **Flux.2 Klein 4b**: Image generation model
- **Wan 2.2 High Noise 6-bit SVDQuant**: Image-to-video model
- **Python**: requests, streamlit, textual, rich; MLX via mlx-lm / mlx-optiq

## Notes

- All processing is local and private
- Stories are saved as Markdown + JSON
- Episode data is stored in `episodes/` folder
- Keyframes are stored under each episode's `images/` directory; video clips remain a manual Draw Things handoff
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
- [`docs/story-success-spec.md`](docs/story-success-spec.md) - story success criteria and approval workflow

## License

Fan project — Star Wars is © Lucasfilm/Disney. This is a non-commercial creative tool.
