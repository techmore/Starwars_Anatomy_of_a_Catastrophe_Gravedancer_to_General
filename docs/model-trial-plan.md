# Sequential model trial plan

This is the first bounded bake-off for the two large local story candidates:

1. `mlx-community/gemma-4-26B-A4B-it-OptiQ-4bit`
2. `mlx-community/Qwen3.8-27B-OptiQ-4bit`

The trials use the same creative seed, daily token ceiling, pipeline, and
single-model process. They run sequentially so the comparison is not polluted
by concurrent unified-memory pressure or one model's weights remaining loaded
while the other starts.

## Run it

The local disk is too full to hold both snapshots safely. Use the mounted
network volume for model files:

```bash
venv/bin/python scripts/run_model_trials.py \
  --download-only \
  --model-root /Volumes/14tb/gravedancer-models
```

After preparation succeeds, run the bounded comparison:

```bash
venv/bin/python scripts/run_model_trials.py \
  --model-root /Volumes/14tb/gravedancer-models \
  --trial-root trial-runs \
  --daily-target-tokens 8000 \
  --seed 2 \
  --download
```

The runner first performs a fixed 512-token smoke probe for each model and
records first-token latency, total latency, approximate token rate, and output
size. Use `--smoke-only` when you want those measurements without waiting for
the multi-day story pipeline.

`--download` is resumable. The run is deliberately four-day/low-budget first;
increase the daily ceiling only after both models complete and the outputs are
worth reading.

## Evidence produced

Each model receives its own directory under `trial-runs/` containing:

- `pipeline.log`: live child output and stage progress;
- `trial.json`: start/end times, wall-clock duration, exit status, model path,
  disk headroom, and saved episode summary;
- `smoke.log` and `smoke-receipt.json`: the short timing probe and its metrics;
- `smoke.json`: the benchmark's machine-readable timing report;
- `storage/`: the generated episode and resumable checkpoints.

`trial-runs/manifest.json` is the batch receipt. It records model preparation
errors separately from generation failures, so a download problem is not
mistaken for a model-quality result.

## Review rubric

After both runs, compare the saved stories blind where practical:

- continuity of injuries, location, equipment, and tactical consequences;
- whether each day escalates instead of resetting;
- character voice and sensory specificity;
- adherence to the supplied outline and daily structure;
- useful prose per minute and editing burden;
- hard failures: empty output, truncation, repeated passages, or broken day
  boundaries.

The timing receipt is a signal, not the quality gate. A faster model only wins
if it remains coherent enough to survive the same continuity review.
