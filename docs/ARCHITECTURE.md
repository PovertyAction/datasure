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
│   ├── id_duplicates_ui.py #   ID duplicate cards UI, with correction controls
│   ├── id_corrections.py   #   Card decisions -> log entries (no Streamlit)
│   ├── gpschecks/          #   GPS validation and outlier mapping; review.py
│                           #   turns outlier corrections and acceptances
│                           #   into log entries (no Streamlit)
│   ├── outliers.py         #   Statistical outlier detection
│   ├── enumerator.py       #   Enumerator performance
│   ├── progress.py         #   Survey progress tracking
│   ├── descriptive.py      #   Descriptive statistics
│   └── backchecks/         #   Back-check comparison workflows; scope.py
│                           #   applies the Duplicates tab's Records to
│                           #   Include filters to the comparison
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
   (`CorrectionProcessor.refresh_existing_corrected_data`). An alias with no
   prep table, such as unprepared backcheck data, is corrected from its raw
   table (`CorrectionProcessor.get_uncorrected_data`)

## Correction log

Every correction and acceptance, from the Correct Data page or a check page,
goes through `CorrectionProcessor` (`processing/corrections.py`) and is
recorded in `corr_log_{alias}` in `logs.duckdb`. Logs are scoped to the
dataset alias, not the report page, so all pages that use a dataset share its
log; backcheck data has its own log under the backcheck alias. The schema,
the `Action` enum and the backfill rules for older logs live in the
Streamlit-free `processing/correction_log.py`, which the replication package
also reads.

- **Actions**: `modify value`, `remove value` and `remove row` change the
  data. They are applied to the corrected table in `corrected.duckdb` and
  replayed, in log order, when the prep data changes. `accept` never changes
  the data and is skipped on replay and in the replication script.
- **`source`**: the page that made the entry: `corrections_page`, `outliers`,
  `constraints`, `duplicates` or `gps`. Entries logged before the column
  existed are backfilled as `corrections_page`.
- **`user`**: who made the entry: the Reviewer name from
  `utils/reviewer.py`, else the OS login. Null for older entries.
- **`accept`**: identified by (`check_type`, `KEY`, `column`), where
  `check_type` is one of `ACCEPT_CHECK_TYPES` (`outliers`, `constraints`,
  `gps`). A GPS acceptance has no column; its `current_value` records the
  latitude and longitude. `CorrectionProcessor.get_active_acceptances` returns
  only acceptances whose recorded value still matches the corrected data, so
  an acceptance lapses when the value changes. `severity` is `hard` on an
  acceptance of a hard constraint violation.
- **Atomic apply**: `CorrectionProcessor.apply_corrections` applies a list of
  entries all or nothing. GPS coordinate changes (one entry per coordinate
  column) and duplicate card saves (one entry per changed record) use it.
- **`status` / `status_reason`**: the outcome of the last replay of each entry.
  An accept row is `Inactive` when `get_active_acceptances` would drop it;
  its status is judged against the final corrected data on replay and on
  every log append. Replay finds each entry's record by the KEY column the
  check config sets for the dataset, or, if none is set, by the first column
  holding the entry's KEY.

The shared correction form lives in `utils/correction_form.py`
(`render_correction_form`, `render_correction_inputs`,
`apply_correction_entries`), with widget keys namespaced per caller. The
Correct Data page renders it in full, and the Outliers page renders its
inputs prefilled with the KEY, column and current value. GPS renders its own
two-coordinate form in `checks/gpschecks/report_ui.py` and reuses only
`get_current_value` and `apply_correction_entries`; duplicates use card
controls that save through `CorrectionProcessor.apply_corrections`.
Check-specific logic that turns a
selection into log entries is kept free of Streamlit: `checks/outliers/review.py`,
`checks/gpschecks/review.py` and `checks/id_corrections.py`.

Backcheck mismatches are never corrected or accepted. Their attributions are
written to the append-only `bc_attribution_{page_name_id}` tables in
`logs.duckdb` by `checks/backchecks/attribution.py`, one table per report
page. The latest entry per survey KEY, backcheck KEY and column applies while
the survey and backcheck values are unchanged, and only feeds the adjusted
error rate.

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
- `cache/{project_id}/settings/` — `logs.duckdb` (import/prep logs, the
  correction logs `corr_log_{alias}`, and the backcheck attribution logs
  `bc_attribution_{page_name_id}`; see [Correction log](#correction-log)),
  JSON settings, and credential metadata
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
is written to JSON. The Mapbox token saved from the GPS Checks settings is also
kept in the keyring, as one entry shared by every project on the machine; a
token set by hand in `secrets.toml` is still read as a fallback. Credentials
are never written to disk, logs, or session state.

## DataFrames and SQL

Polars is the primary DataFrame library; pandas appears only at interop
boundaries (some checks, DuckDB `fetchdf`, matplotlib/seaborn charts). DuckDB
table names pass through `_validate_table_name()`; user-supplied values in SQL
must be parameterized, never f-string interpolated.

## Conventions

- Imports are always absolute: `from datasure.utils import ...`
- Assets resolve relative to the package, not the CWD:
  `Path(__file__).parent.parent / "assets"`
