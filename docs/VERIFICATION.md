# Verification

Run these checks to confirm the current implementation state:

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile app.py src/components/*.py src/utils/*.py tests/*.py
```

## What these checks cover

- Story generation prompt structure and parsing
- Draw Things client fallback behavior
- Episode storage normalization and archive output
- Full local workflow smoke coverage

## Notes

- These checks assume the repo is using the current Streamlit prototype shell.
- The machine-readable `DrawThings` labels remain part of the parser/storage compatibility contract.

