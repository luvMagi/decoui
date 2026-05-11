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
uv publish
```

Enter your PyPI credentials when prompted, or set them as environment variables to skip the prompt:

```bash
UV_PUBLISH_USERNAME=__token__
UV_PUBLISH_PASSWORD=pypi-your-api-token
```

### 4. Verify

Check the release landed at: https://pypi.org/project/decoui/
