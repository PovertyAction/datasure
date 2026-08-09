---
name: streamlit
description: DataSure-specific Streamlit patterns (asset paths, cache directory resolution). For general Streamlit development (widgets, layouts, session state, caching, theming, deployment, custom components), use the developing-with-streamlit skill instead.
---

# DataSure Streamlit Patterns

This skill covers Streamlit patterns specific to DataSure's codebase and packaging model.
For everything else Streamlit-related, use the `developing-with-streamlit` skill, which
routes to version-matched reference docs bundled with the installed Streamlit package.

## Asset Management

Views resolve assets relative to the installed package, not the CWD:

```python
from pathlib import Path

# Package-relative asset paths
assets_dir = Path(__file__).parent.parent / "assets"
logo_path = assets_dir / "logo.png"

if logo_path.exists():
    st.image(str(logo_path), width=200)
```

## Cache Directory Handling

DataSure resolves its cache directory via
`datasure.utils.cache_utils.get_cache_base_dir()` — don't reimplement this logic inline.
It picks between a development location and an installed-package location:

- **Development** (a `pyproject.toml` exists in the working directory): `./cache/`
- **Installed, Windows**: `%APPDATA%/datasure/cache/`
- **Installed, Linux/macOS**: `$XDG_DATA_HOME/datasure/cache/` or
  `~/.local/share/datasure/cache/`

```python
from datasure.utils.cache_utils import get_cache_base_dir

cache_dir = get_cache_base_dir()
```

See `src/datasure/utils/cache_utils.py` for the full implementation, including
per-project (`ensure_cache_dir`) path helpers.
