# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with
code in this repository.

## Project Overview

**DataSure** is IPA's (Innovations for Poverty Action) Data Management System:
a Streamlit web application for data quality monitoring and high-frequency
checks (HFCs) on survey data collection projects. It imports data from
SurveyCTO or local files, stores it in per-project DuckDB databases, runs
configurable data quality checks, and renders interactive report pages.

- Python 3.11+, src/ layout, package name `DataSure`, CLI command `datasure`
- Build backend: `uv_build`; package manager: uv (`uv.lock` committed)
- Version: static in `pyproject.toml`, managed with `uv version --bump`
  (`src/datasure/__init__.py` is intentionally empty)
- Distribution: PyPI only. There is no PyInstaller/NSIS/winget packaging.

## Development Commands

Run commands with `just` (cross-platform; PowerShell on Windows, bash on
Linux/macOS). `just --list` shows all recipes.

```bash
# Environment
just get-started          # Install tooling + create venv
just venv                 # uv sync + pre-commit install
just update-reqs          # Re-lock dependencies, autoupdate pre-commit

# Run the app
uv run datasure           # Via the CLI entry point (localhost:8501)
just datasure-dev         # Via streamlit run on the source tree

# Code quality - run ALL of this before committing
just lint-py              # ruff check
just fmt-python           # ruff format (CI enforces this too, not just lint)
uv tool run pre-commit run --all-files   # Everything CI's pre-commit runs

# Tests
just test                 # Full suite
just test-cov             # With terminal coverage report
just test-cov-xml         # XML coverage (used by CI/SonarQube)
uv run python -m pytest tests/checks/test_summary.py   # Single file
uv run python -m pytest -k "test_missing"               # By pattern

# Versioning and release (see CONTRIBUTING.md for the full process)
just version              # Show current version
just bump-patch           # Bump + commit + tag (also -minor/-major variants)
just push-all             # Push commits and the version tag
just build-package        # uv build (wheel + sdist into dist/)
```

### Mandatory pre-commit workflow

CI runs the full pre-commit suite, which includes **ruff format** in addition
to ruff check. `just lint-py` alone is not sufficient: a commit can pass
linting and still fail CI on formatting. Before every commit:

1. `just lint-py` and fix all errors (never ignore them)
2. `just fmt-python` (or run the full pre-commit suite)
3. Common Ruff failures: F841 unused variables (prefix `_`), B007 unused
   loop variables, TRY301 raise-inside-try (move to a helper), D-series
   docstring rules (NumPy convention)

Error-handling conventions (specific exceptions in library code,
translate-and-reraise with `from e`, logged catch-alls only at UI
boundaries) are documented in CONTRIBUTING.md.

## Project Structure

```text
src/datasure/
├── app.py                  # Streamlit entry point: session state + st.navigation
├── cli.py                  # argparse CLI; launches Streamlit (localhost:8501)
├── assets/                 # Logos and demo CSV data bundled with the package
├── checks/                 # Data quality check modules (one per check type)
│   ├── summary.py          #   Overall data quality summary
│   ├── missing.py          #   Missing data analysis
│   ├── duplicates.py       #   Duplicate detection
│   ├── gpschecks.py        #   GPS validation and outlier mapping
│   ├── outliers.py         #   Statistical outlier detection
│   ├── enumerator.py       #   Enumerator performance
│   ├── progress.py         #   Survey progress tracking
│   ├── descriptive.py      #   Descriptive statistics
│   └── backchecks.py       #   Back-check comparison workflows
├── connectors/
│   ├── scto.py             # SurveyCTO download/UI (uses utils/scto_api.py)
│   └── local.py            # Local file import (csv/xlsx/xls/json/dta)
├── processing/
│   ├── prep.py             # Data preparation operations (Polars)
│   └── corrections.py      # Data correction application
├── replication/            # Stata/Python replication package export
│   ├── package_builder.py, script_generators.py, prep_script_generator.py,
│   ├── scto_import_generator.py, codebook.py, readme.py
├── models/
│   ├── schemas.py          # Pydantic models
│   └── enums.py            # Prep action/method enums
├── utils/
│   ├── duckdb_utils.py     # DuckDB table save/get/remove (validated names)
│   ├── cache_utils.py      # Cache directory resolution (dev vs installed)
│   ├── config_utils.py     # ConfigurationService: report pages, output views
│   ├── settings_utils.py   # JSON settings persistence
│   ├── secure_credentials.py # OS-keyring credential storage (no plaintext)
│   ├── scto_api.py         # SurveyCTO REST client (requests + basic auth)
│   ├── prep_utils.py, dataframe_utils.py, chart_utils.py,
│   ├── navigations_utils.py, onboarding_utils.py (demo project)
└── views/                  # Streamlit pages (top-level page scripts)
    ├── start_view.py       # Project selection/creation
    ├── import_view.py      # Credentials + data import
    ├── prep_view.py        # Data preparation
    ├── config_view.py      # Check configuration
    ├── correction_view.py  # Data corrections
    ├── replication_view.py # Replication package export
    ├── output_view_template.py  # Template for generated report pages
    └── output_view_N.py    # GENERATED per report page; gitignored
```

`connectors/script.py` is an empty placeholder slated for removal
(issue 194). The `archived/` directory holds legacy code and is gitignored.

### Generated output views

Report pages are created at runtime: `ConfigurationService`
(`utils/config_utils.py`) copies `output_view_template.py` to
`views/output_view_{N}.py` for each configured report page, and `app.py`
registers them in `st.navigation`. The numbered files match the gitignore
pattern `output_view_?.py` - never commit them, and never edit them directly
(edit the template).

## Architecture

### Data flow

1. **Import** (`import_view.py` + connectors): SurveyCTO API or local files
2. **Storage**: per-project DuckDB databases via `duckdb_utils.py`
3. **Preparation** (`prep_view.py` + `processing/prep.py`): Polars
   operations recorded in a prep log for reproducibility
4. **Checks** (`config_view.py` + `checks/`): configurable per-page checks
5. **Reports** (generated output views): charts and tables per check
6. **Corrections / replication**: apply corrections; export a replication
   package that reproduces the pipeline outside DataSure

### Cache and data locations (`utils/cache_utils.py`)

- **Development** (a `pyproject.toml` exists in the working directory):
  `./cache/`
- **Installed, Windows**: `%APPDATA%/datasure/cache/`
- **Installed, Linux/macOS**: `$XDG_DATA_HOME/datasure/cache/` or
  `~/.local/share/datasure/cache/`

Per project (UUID-keyed): `cache/{project_id}/data/` holds the DuckDB
databases `raw.duckdb`, `prep.duckdb`, `corrected.duckdb`;
`cache/{project_id}/settings/` holds `logs.duckdb` (import/prep logs),
JSON settings, and credential metadata. `cache/projects.json` is the
project registry. The `cache/` directory is gitignored.

### Session state

`app.py` initializes the cross-page session state. Key variables:
`st_project_id` (current project), `st_raw_dataset_list`,
`st_prep_dataset_list`, page handles (`st_prep_data_page`,
`st_output_pages`, ...). View modules are page scripts: they run top to
bottom on every rerun and guard on `st_project_id` (calling `st.stop()`
when no project is selected).

### Credentials

SurveyCTO passwords are stored in the OS keyring
(`utils/secure_credentials.py`); only non-sensitive metadata (server,
username) is written to JSON. Never write credentials to disk, logs, or
session state.

### DataFrames

Polars is the primary DataFrame library; pandas appears at interop
boundaries (some checks, DuckDB `fetchdf`, matplotlib/seaborn charts).
DuckDB table names pass through `_validate_table_name()`; user-supplied
values in SQL must be parameterized, never f-string interpolated.

## Testing

- pytest with coverage; **`fail_under = 80`** (pyproject `[tool.coverage]`)
- Markers: `slow`, `integration`, `unit` (`-m "not slow"` to skip slow)
- `tests/conftest.py` provides shared fixtures, including:
  `sample_dataframe`, `sample_gps_data`, `missing_data`, `date_format_data`,
  `backcheck_survey_data`/`backcheck_data`, `mock_streamlit_session`,
  `mock_st`, `settings_file`; plus autouse fixtures `mock_database_functions`
  (no real DB files needed) and `cleanup_test_cache`
- `tests/views/` has its own conftest that installs a module-level
  streamlit mock so view page scripts can be imported; follow the pattern in
  `tests/views/test_prep_view.py` (configure the shared mock, patch utils at
  source during import, then test module functions directly)
- Layout mirrors src: `tests/{checks,connectors,processing,replication,
  utils,views,models}/`

## Build, CI, and Release

- **CI** (`.github/workflows/`): pre-commit + tests + SonarQube run on
  pushes and PRs; pushing a `v*` tag triggers the build-and-publish
  pipeline (wheel/sdist via `uv build`, publish to PyPI, GitHub release).
  Pre-release versions (a/b/rc) go to Test PyPI; finals go to PyPI.
- **Release process**: update CHANGELOG.md and RELEASENOTES.md, then
  `just bump-patch|minor|major` (commits and tags), then `just push-all`.
  CONTRIBUTING.md documents the full process and documentation guides.
- **Version**: one source of truth in `pyproject.toml`, edited only via
  `uv version`. At runtime `cli.py` reads it from package metadata.

## Common Tasks

### Adding a data quality check

1. Create the module in `src/datasure/checks/` following an existing one
   (e.g. `missing.py`): a report function that takes prepared data plus
   settings and renders Streamlit output
2. Wire it into check configuration (`views/config_view.py` /
   `utils/config_utils.py`) and the output view template if needed
3. Add `tests/checks/test_<name>.py` using the conftest fixtures

### Adding a data connector

1. Create the module in `src/datasure/connectors/` (see `local.py` for the
   pattern: Pydantic validation, a render form, and a load function that
   saves via `duckdb_save_table`)
2. Add it to the import-type options in `views/import_view.py`
3. Add tests in `tests/connectors/`

### Modifying views

Views are Streamlit page scripts with module-level code. Use
package-relative asset paths (`Path(__file__).parent.parent / "assets"`),
follow the existing session-state naming, and keep `st.rerun()` out of
broad try blocks (its control-flow exception must not be caught).

## Troubleshooting

- **Imports**: always absolute (`from datasure.utils import ...`)
- **Assets**: resolve relative to the package, not the CWD
- **Session state corruption**: all cross-page keys are initialized in
  `app.py`; check there first
- **Windows**: the suite must run cleanly with plain
  `uv run python -m pytest` - if pytest dies with INTERNALERROR, a test is
  patching `os.name`/`pathlib` without context-managed cleanup
- **Streamlit pages failing on import in tests**: the module-level mock in
  `tests/views/conftest.py` must be active; see existing view tests
