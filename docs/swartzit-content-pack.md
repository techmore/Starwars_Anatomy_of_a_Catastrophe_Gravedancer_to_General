# Swartzit content-pack adapter

This project can run as an optional Swartzit extension. Swartzit launches
`scripts/swartzit_pack_runner.py` as an external process; it does not import
this project or require it in the base Swartzit installation.

The adapter currently registers `starwars.gravedancer`. Its output is the
generic `content-package.v1` manifest:

- one `series` package;
- one ordered `article` unit per generated day;
- a compact feed item for the timeline;
- provenance for seed, model, source directory, and completion state;
- local image assets when an episode already contains them.

Existing episodes are importable without another model call:

```bash
python3 scripts/swartzit_pack_runner.py --backfill episodes/<episode-id>
```

When Swartzit launches the adapter it sets
`SWARTZIT_RUNNER_PROTOCOL=jsonl` and `RUNNER_PACK_OPTIONS_JSON`. The pipeline
emits progress and a checkpoint after each completed day. The worker can then
pause at that boundary and later resume from the local checkpoint.
`RUNNER_RESUME_CHECKPOINT_JSON` is available to packs that want to make their
own resume UI or bookkeeping decisions.

The current host publication is one compact feed item per package. The
ordered day units and their optional media remain in the manifest so an
article renderer can be added later without changing this adapter contract.

## Local model defaults

The pack defaults to Gemma 4 E4B IT OptiQ for fast story generation and Gemma
4 E2B for recaps. Override `model`, `story_model`, `recap_model`, or
`visual_model` in the runner options when the machine has a larger local model
available. `days` is bounded to 3–8 so a test run stays reviewable.

## Draw Things defaults

Text generation is independent from image generation. Set
`generate_images: true` only after the text path is healthy. The initial CLI
recipe uses the locally verified `flux_1_schnell_q5p.ckpt`; the optional
`draw_things.loras` list is passed through as Draw Things `config-json`.
LoRAs are never downloaded or guessed. Use only a file that is already in the
configured Draw Things models directory and matches the model family.

## Headless ComfyUI backend

The image phase also supports a localhost-only ComfyUI worker. This is an
optional backend; it does not change Swartzit’s deployment bind and it does
not make ComfyUI publicly reachable. ComfyUI must have a checkpoint installed
in its `models/checkpoints` directory. The included
`config/comfyui/sd15-api.json` is a minimal SD 1.x API-format workflow with
placeholders for the prompt, dimensions, sampling settings, seed, and model.

Example runner options:

```json
{
  "generate_images": true,
  "image_mode": "day",
  "max_images": 1,
  "draw_things": {
    "backend": "comfyui",
    "url": "http://127.0.0.1:8188",
    "workflow": "config/comfyui/sd15-api.json",
    "model": "your-checkpoint.safetensors",
    "width": 1024,
    "height": 576,
    "steps": 8,
    "cfg": 6.5
  }
}
```

The workflow must be ComfyUI’s API export (node id keys with `class_type` and
`inputs`), not the regular editor workflow JSON. A different model family or
custom-node graph can be used by supplying its own API workflow file; the
adapter keeps the same image-generation contract for the pack.
