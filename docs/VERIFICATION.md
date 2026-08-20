# Verification

Run these checks to confirm the current implementation state:

```bash
pytest -q
python3 -m unittest discover -s tests -v
python3 -m py_compile app.py src/components/*.py src/utils/*.py tests/*.py
python3 -m compileall -q app.py src tests
python3 scripts/benchmark_model.py --model "lmstudio:ornith-1.5-9b-mlx" --max-tokens 256
```

## What these checks cover

- Story generation prompt structure and parsing
- Draw Things client fallback behavior
- Episode storage normalization and archive output
- Storage path-safety, atomic writes, and malformed-file recovery
- Per-session state isolation and saved-episode loading
- Full local workflow smoke coverage
- Bounded local-model latency and throughput measurement (does not create episodes)

## Notes

- These checks assume the repo is using the current Streamlit prototype shell.
- The machine-readable `DrawThings` labels remain part of the parser/storage compatibility contract.
