# DataSure Architecture

Technical reference for the DataSure codebase: package layout, data flow,
storage locations, and the runtime conventions that views and checks rely on.
For contribution workflow, code quality rules, and the release process, see
[CONTRIBUTING.md](../CONTRIBUTING.md).

## Project facts

- Python 3.11+, `src/` layout, package name `DataSure`, CLI command `datasure`
- Build backend: `uv_build`; package manager: uv (`uv.lock` is committed)
- Version: a single static value in `pyproject.toml`, edited only via
  `uv version --bump` (`src/datasure/__init__.py` is intentionally empty)
- Distribution: PyPI only — there is no PyInstaller/NSIS/winget packaging

## Package layout

```text
src/datasure/
├── app.py                  # Streamlit entry point: session state + st.navigation
├── cli.py                  # argparse CLI; launches Streamlit (localhost:8501)
├── assets/                 # Logos and demo CSV data bundled with the package
├── checks/                 # Data quality check modules (one per check type)
│   ├── summary.py          #   Overall data quality summary
│   ├── missing.py          #   Missing data analysis
│   ├── duplicates.py       #   Duplicate detection
│   ├── id_duplicates.py    #   ID duplicate/unmatched cards logic (no Streamlit)
│   ├── id_duplicates_ui.py #   ID duplicate cards UI
│   ├── gpschecks.py        #   GPS validation and outlier mapping
│   ├── outliers.py         #   Statistical outlier detection
│   ├── enumerator.py       #   Enumerator performance
│   ├── progress.py         #   Survey progress tracking
│   ├── descriptive.py      #   Descriptive statistics
│   └── backchecks.py       #   Back-check comparison workflows
├── connectors/
│   ├── scto.py             # SurveyCTO download/UI (uses utils/scto_api.py)
│   └── local.py            # Local file import (csv/xlsx/xls/json/dta/parquet)
├── processing/
│   ├── prep.py             # Data preparation operations (Polars)
│   ├── corrections.py      # Corrections and accept entries (CorrectionProcessor)
│   └── correction_log.py   # Correction log schema/backfill, Action enum (no Streamlit)
├── replication/            # Stata/Python replication package export
├── models/
│   ├── schemas.py          # Pydantic models
│   └── enums.py            # Prep action/method enums
├── utils/                  # Shared utilities (DuckDB, cache, config, charts,
│                           # credentials, SurveyCTO API, UI helpers, ...)
│   └── correction_form.py  #   Shared correction form used across pages
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

The `archived/` directory holds legacy code and is gitignored.

## Data flow

1. **Import** (`views/import_view.py` + `connectors/`): SurveyCTO API or local
   files
2. **Storage**: per-project DuckDB databases via `utils/duckdb_utils.py`
3. **Preparation** (`views/prep_view.py` + `processing/prep.py`): Polars
   operations recorded in a prep log for reproducibility
4. **Checks** (`views/config_view.py` + `checks/`): configurable per-page checks
5. **Reports** (generated output views): charts and tables per check
6. **Corrections / replication**: apply corrections; export a replication
   package that reproduces the pipeline outside DataSure. Once an alias has a
   corrected table, any change to its prep data (a re-import, a prep step
   added or removed, or a project bundle re-seeding its prep steps) rebuilds it
   by replaying the correction log against the new prep output
   (`CorrectionProcessor.refresh_existing_corrected_data`)

## Generated output views

Report pages are created at runtime: `ConfigurationService`
(`utils/config_utils.py`) copies `views/output_view_template.py` to
`views/output_view_{N}.py` for each configured report page, and `app.py`
registers them in `st.navigation`. The numbered files match the gitignore
pattern `output_view_?.py` — never commit them and never edit them directly;
edit the template instead.

## Cache and data locations

Resolved by `utils/cache_utils.py`:

- **Development** (a `pyproject.toml` exists in the working directory):
  `./cache/`
- **Installed, Windows**: `%APPDATA%/datasure/cache/`
- **Installed, Linux/macOS**: `$XDG_DATA_HOME/datasure/cache/` or
  `~/.local/share/datasure/cache/`

Per project (UUID-keyed):

- `cache/{project_id}/data/` — the DuckDB databases `raw.duckdb`,
  `prep.duckdb`, `corrected.duckdb`
- `cache/{project_id}/settings/` — `logs.duckdb` (import/prep logs, and the
  append-only backcheck attribution logs `bc_attribution_{page_name_id}`
  written by `checks/backchecks/attribution.py`), JSON settings, and
  credential metadata
- `cache/projects.json` — the project registry
- `cache/user_settings.json` — per-user preferences, currently the
  "Reviewer name" recorded as `user` in correction logs
  (`utils/reviewer.py`). Display names only, never credentials.

The `cache/` directory is gitignored.

## Session state

`app.py` initializes all cross-page session state. Key variables:
`st_project_id` (current project), `st_raw_dataset_list`,
`st_prep_dataset_list`, and page handles (`st_prep_data_page`,
`st_output_pages`, ...). View modules are page scripts: they run top to bottom
on every rerun and guard on `st_project_id`, calling `st.stop()` when no
project is selected. If cross-page state looks corrupted, check `app.py` first.

## Credentials

SurveyCTO passwords are stored in the OS keyring
(`utils/secure_credentials.py`); only non-sensitive metadata (server, username)
is written to JSON. Credentials are never written to disk, logs, or session
state.

## DataFrames and SQL

Polars is the primary DataFrame library; pandas appears only at interop
boundaries (some checks, DuckDB `fetchdf`, matplotlib/seaborn charts). DuckDB
table names pass through `_validate_table_name()`; user-supplied values in SQL
must be parameterized, never f-string interpolated.

## Conventions

- Imports are always absolute: `from datasure.utils import ...`
- Assets resolve relative to the package, not the CWD:
  `Path(__file__).parent.parent / "assets"`
