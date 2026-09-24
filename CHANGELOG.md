# Changelog

## 0.2.0

- Adds a native Ubuntu/Ollama backend for the content-pack workflow while
  preserving MLX defaults on macOS.
- Adds explicit `ollama:<model>` routing, health checks, streaming coverage,
  and source-install guidance for the Swartzit article-unit adapter.
- Adds the Linux Ollama 16K context drop-in needed to keep multi-day outlines
  from truncating at the default 4K window.

## 0.1.0

- Adds the optional Swartzit `content-package.v1` adapter for the
  Gravedancer to General pack.
- Emits JSONL progress, day checkpoints, cancellation frames, and ordered
  article units while keeping the generator independent from Swartzit core.
- Adds existing-episode backfill manifests, bounded day overrides, and
  Draw Things CLI LoRA configuration forwarding.
