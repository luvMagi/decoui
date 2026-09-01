# Publishing to PyPI

## Steps

### 1. Bump the version

Edit `pyproject.toml` — update the `version` field:

```toml
[project]
version = "x.y.z"
```

### 2. Build

```bash
uv build
```

Output goes to `dist/`.

### 3. Publish

```bash
uv run twine upload dist/*
```

Credentials are read automatically from `~/.pypirc` — no prompt needed.

### 4. Verify

Check the release landed at: https://pypi.org/project/decoui/
