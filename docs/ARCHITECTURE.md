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
│   ├── catalogue.py        #   Every check on a check page: slug, label,
│                           #   icon, group, status, render and headline
│   ├── context.py          #   PageConfig, CheckData, CheckContext
│   ├── health.py           #   Summary's check health rows, cached headlines
│   ├── summary.py          #   Data, submission and progress summary
│   ├── missing.py          #   Missing data analysis
│   ├── duplicates.py       #   Duplicate detection
│   ├── id_duplicates.py    #   ID duplicate/unmatched cards logic (no Streamlit)
│   ├── id_duplicates_ui.py #   ID duplicate cards UI, with correction controls
│   ├── id_corrections.py   #   Card decisions -> log entries (no Streamlit)
│   ├── gpschecks/          #   GPS validation and outlier mapping; review.py
│                           #   turns outlier corrections and acceptances
│                           #   into log entries (no Streamlit)
│   ├── outliers/           #   Statistical outlier detection
│   ├── enumerator/         #   Enumerator performance
│   ├── progress.py         #   Survey progress tracking
│   ├── descriptive.py      #   Descriptive statistics
│   └── backchecks/         #   Back-check comparison workflows; scope.py
│                           #   applies the Duplicates check's Records to
│                           #   Include filters to the comparison
├── connectors/
│   ├── scto.py             # SurveyCTO download/UI (uses utils/scto_api.py)
│   └── local.py            # Local file import (csv/xlsx/json/dta/parquet)
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
│   ├── correction_form.py  #   Shared correction form used across pages
│   ├── navigation.py       #   Navigation resolver and status types (no Streamlit)
│   └── nav_ui.py           #   Shared navigation controls and render wrapper
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
5. **Reports** (generated output views): charts and tables per check. Each
   dataset is read from the first of its `corrected`, `prep` and `raw` tables
   that exists (`load_data_with_fallback`). A table with no rows still counts,
   so a prep step or correction that removed every record shows an empty
   dataset rather than older data
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

### Check navigation

A check page draws its checks from the catalogue in `checks/catalogue.py`.
Each `CheckEntry` has a slug, short label, icon, group, a `render` function
and a `status` function, plus optional `setup`, `settings`, `setup_hint`
and `headline` fields. Adding an entry is the only change needed for a check
to appear.

- **Status.** Each check module exposes a cheap `<check>_status(...)` that
  returns a `StatusResult` (`CheckStatus` ready, not set up, not applicable or
  error, plus a reason) from page configuration and data shape only. It never
  computes results. `catalogue.nav_items` turns the statuses into `NavItem`s;
  a status function that raises gives that check the error status.
- **Selection.** `utils/navigation.py` is the pure resolver (no Streamlit):
  `resolve_nav` picks a valid URL value, then the saved selection, then the
  default (Summary); an invalid URL value goes straight to the default. And
  `group_selection` picks the remembered or first check when the group
  changes. `utils/nav_ui.py` wraps it for Streamlit and
  is meant to be shared by every page that picks one item from many.
- **Lazy rendering.** `render_checks` in the template runs only the selected
  check. A check that is not ready shows a standard empty state with its
  reason; a not-set-up check then shows its settings (`setup`, or its report,
  which starts with its settings), and a not-applicable check shows its
  settings section alone (`settings`; Outliers, GPS and Backchecks expose
  `<check>_settings_section`, which their reports also start with). The
  not-set-up message ends with the entry's `setup_hint`, "Set it up below."
  by default; Backchecks points to the page linked below instead. Summary computes the outlier and backcheck
  rates inside its own render, so they only run when Summary is shown.
- **Health rows.** Summary ends with one row per other check, grouped by
  navigation group under a shared column header (`checks/health.py`:
  `health_rows` builds them, `render_health_rows` draws them). A catalogue
  entry's optional `headline` function returns a `CheckHeadline`
  (`checks/headline.py`): the outstanding value and its detail line, the
  outstanding number, the resolved count and an informational flag, each
  computed the way the check computes it but without rendering it. A row's
  state (`RowState`) is derived, not stored: grey not set up or not
  applicable and red error come from the config-only `CheckStatus`; a ready
  row is red if its headline raised (a headline raises, through
  `settings_no_longer_fit`, rather than returning None when the saved
  settings no longer fit the data), amber (flagged) if it has more than 0
  outstanding and is not informational, else green. Headlines run only for
  ready checks and are cached in a small in-process LRU keyed on the page's
  data (row hashes), settings files (content hash, leaving out
  [view state](#view-state)), the logs and intermediate databases
  (modification time and size) and today's date. A headline that raises
  is logged, shown on its row and not cached; the other rows still render.
  The row buttons call `select_nav_item`, so they select the check exactly
  as the navigation does. The navigation itself never shows counts.
- **Render wrapper.** Every check renders through `nav_ui.run_guarded`. An
  exception becomes an error state with the traceback in an expander, is
  logged, and is remembered so the navigation marks the check until it
  renders cleanly. `st.stop()` and `st.rerun()` raise `BaseException`
  subclasses, so they pass through. The navigation is drawn after the check,
  into a container placed above it, so the mark appears on the same run.
- **Widget state.** Streamlit drops the state of widgets that are not drawn,
  so a check's widgets are rebuilt from its saved settings each time it is
  opened. Settings loaders must therefore read the settings file directly,
  not through `st.cache_data`. Filter, selection and sort widgets that are
  not check settings are kept as [view state](#view-state).

### View state

`utils/view_state.py` keeps personal view settings in a `view_state` section
of a settings JSON file, so they survive switching checks and new sessions.
On a check page this is the page settings file
(`page_{page_name_id}_settings.json`):

```json
{
  "duplicates": {"survey_id": "hhid"},
  "view_state": {
    "selected": "duplicates",
    "scopes": {"duplicates": {"iddup_survey_sort": "Latest date"}}
  }
}
```

- **Selection.** `saved_selection` / `save_selection` hold the last selected
  item. `render_checks` passes it to `nav_ui.resolve_selection` as `saved`,
  so precedence is a valid `?check=` URL value, then the selection made
  earlier in this session, then the saved selection, then Summary. An
  invalid `?check=` value opens Summary. A saved slug that is no longer in
  the catalogue is ignored.
- **Widget values.** `ViewState(settings_file, scope).bind(key, options=...,
  multi=..., on_change=..., **initial)` returns the widget's `key` and
  `on_change` keyword arguments. Before the widget is drawn, it copies a
  saved value into `st.session_state` when this session has none, and it
  saves the value when the user changes it. A saved value that is not in
  `options` is removed and the widget shows its default; a multiselect keeps
  only the values that still exist. The widget's own default (`index`,
  `default`, `value`) goes through `initial`, so it is left out once session
  state holds a value. `bind_widget(view, key, ...)` does the same for
  helpers that may have no view.
- **Displayed value.** Switching to another check and straight back can
  interrupt the run that would clear a widget's value, so the value survives
  in session state and still filters the output, but the redrawn widget
  shows its default: Streamlit only sends a value to the browser when code
  sets it. `show_session_value(key)` sets it again before the widget is
  drawn. `bind` and `keep` call it.
- **Kept for the session.** `ViewState.keep(key, ...)` keeps a search box's
  value when the user switches to another check and back, without saving
  it: a new session starts with an empty box. The value is kept per settings
  file and scope, so another check page does not inherit it. Used by the
  duplicates "Search by ID or KEY" box.
- **Scopes.** A check's scope is its catalogue slug (`VIEW_SCOPE` in each
  check module). "Reset filters" (`reset_filters_button`) calls
  `ViewState.reset_widgets`, which clears only that scope's saved values and
  their session state. It does not touch the check's own settings. Each
  check draws it beside its settings expander by wrapping the settings call
  in `reset_filters_beside(check_view(setting_file))`; Missing Values and
  Descriptive Stats, which have no settings section, wrap their title.
  Corrections (scope: the check page) draws the action above the selected
  page, and Prepare Data (scope: the dataset) beside the "Preview Prepared
  Data" header.
- **Not saved.** Pagination, search boxes and inputs inside dialogs or
  popovers are never bound, so they start fresh in a new session. Bound
  today: Summary's "Progress by" column and time period; the Progress time
  period and extra attempted-interview columns; the Missing Values
  threshold, date column, group-by and compare columns, all-columns toggle
  and correlation columns;
  the duplicates dataset switcher, card sort, column selector and extra
  report columns; the outliers table toggles, inspected column and extra
  constraint violation columns; the GPS map colour, filter and category
  values, configuration choices, detection method, clustering column,
  distance threshold and Show reviewed toggle; the enumerator summary
  information pills, productivity period and week start, and the statistics
  columns, statistics, period and week start; the backcheck comparison
  filters, productivity period and week start, and staff statistics view;
  the Descriptive Stats histogram and value counts choices; and the Prepare
  Data preview's "Columns to show". Descriptive
  Stats saves its column selection to DuckDB, and the GPS outlier detection
  sliders (neighbours, expected proportion) are analysis parameters with
  data-dependent bounds, so neither is view state.
- **Legacy values.** Older versions saved the Summary, Progress, Missing
  Values, Descriptive Stats, enumerator, backcheck and outliers view values
  above, and the duplicates extra report columns, with the check's settings. Their
  `check_view` (`view_factory(..., legacy=(section, keys))`) runs
  `ViewState.adopt_legacy` when opened: a legacy value moves into the
  check's scope (unless one is already there) and leaves the settings
  section, so old files still load and the value then behaves as view
  state. Configuration (Progress and Summary columns and targets, Progress
  consent and outcome) stays with the check's settings.
- **Not shared.** View state is personal. `without_view_state` drops it from
  project configuration exports, together with legacy values not yet moved
  (`LEGACY_VIEW_KEYS`, which `view_factory` checks each check's legacy keys
  against), and applying a configuration (a project
  template) keeps the local `view_state` and ignores any in the bundle
  (`utils/project_config.py`). The replication package never reads settings
  files.
- **Other pages.** `ViewState` and the selection functions take any settings
  file. Prepare Data keeps the selected dataset in
  `settings/prep_view_settings.json`. Corrections keeps the selected check
  page in `settings/correction_view_settings.json`, with one scope per check
  page (its `page_name_id`) holding the Survey data / Backcheck data choice
  and the Correction Log filters.
- **Last viewed check page.** `render_checks` records the `page_name_id` of
  the check page being viewed as `view_state.last_check_page` in the
  project-level `settings/project_view_settings.json`
  (`nav_ui.PROJECT_VIEW_FILE`, `nav_ui.LAST_CHECK_PAGE`), writing only when
  it changes (`view_state.remember`). With no `page` URL value, Corrections
  reads the record, forgets it (`forget_remembered`) and selects that check
  page, so it opens on the page the user was reviewing, also in a new
  session; forgetting it keeps a page chosen on Corrections until another
  check page is viewed. With a `page` URL value the URL wins and the record
  is kept for the next visit without one.

### Prepare Data and Corrections navigation

Both pages draw one wrapping row of pills with `nav_ui.draw_nav` (items with
no group) and render only the selected item through `nav_ui.run_guarded`.

- **Prepare Data** (`views/prep_view.py`). Before anything is drawn,
  `seed_prep_from_raw` runs for **every** dataset: with no prep steps logged,
  raw data is copied into the prep table. This must not move into the
  selected dataset's render, because Configure Checks and the replication
  package read columns only from prep. `dataset_status` dims a dataset with
  no imported rows (missing, or zero rows and no steps); a dataset whose
  steps removed every row stays ready so the step can be removed. The
  dataset's position in the sorted list (`step_index`) still namespaces its
  widget keys and is passed to `prep_add_step` / `prep_remove_step`.
- **Corrections** (`views/correction_view.py`). Item slugs are page
  `page_name_id`s; the selected page's position in `check_config` is the
  index `render_correction_tab` and `load_tab_config` use. `check_page_status`
  dims a page with no survey KEY column or no survey data in the corrected,
  prep or raw database (it only checks the table exists). Precedence: a valid
  `?page=` value, then the check page last viewed (see
  [View state](#view-state)), then the selection made earlier in this
  session or saved, then the first page.

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
  correction logs `corr_log_{alias}`, the backcheck attribution logs
  `bc_attribution_{page_name_id}`, see [Correction log](#correction-log),
  each check page's check tables, such as the Descriptive Stats column
  selection `descriptive_columns_{page_name_id}`, and the project's missing
  codes `missing_codes_{project_id}`), JSON settings (including
  each check page's, Prepare Data's and Corrections'
  [view state](#view-state)), and credential metadata
- `cache/projects.json` — the project registry
- `cache/user_settings.json` — per-user preferences, currently the
  "Reviewer name" recorded as `user` in correction logs
  (`utils/reviewer.py`). Display names only, never credentials.

Check settings are per page: a page's JSON settings file and its
`{prefix}_{page_name_id}` tables in `logs.duckdb`. Data a check derives from
its settings is computed when the report runs, cached on the data and the
settings, and not stored; the Enumerator report's consent and completion
flags work this way. Older versions kept the Descriptive Stats selection
project-wide in `selected_columns_df` in `data/intermediate.duckdb`; a page
with no selection of its own is seeded from it once, filtered to the page's
columns, and the old table is left in place. Exporting a page that has no
selection table yet exports the old selection's selected rows as the page's
own. Importing a page bundled without a selection writes an empty one, so the
page is not seeded from the destination's old selection.

The `cache/` directory is gitignored.

## Project configuration bundle

`utils/project_config.py` exports a project's setup to one JSON file
(`ProjectConfigBundle` in `models/schemas.py`) and applies it to a new or
existing project. The bundle holds import sources, prep steps, one
`ProjectPageBundle` per check page, the missing codes and the corrections.
Credentials, file paths, survey data and [view state](#view-state) never
travel.

- **Check tables.** `CHECK_TABLE_PREFIXES` lists the per-page tables that
  travel: `duplicates`, `outliers`, `gps_columns`, `backchecks`,
  `descriptive_columns` and `bc_attribution`. Export reads
  `{prefix}_{page_name_id}` from `logs.duckdb` into
  `ProjectPageBundle.check_tables` (rows keyed by prefix) and
  `check_table_schemas` (each column's dtype encoded as JSON), skipping empty
  tables, so list and date columns are restored exactly. The prefixes, the
  registry and the `check_table_name()` / `missing_codes_table_name()`
  helpers live in `utils/duckdb_utils.py`; checks name their tables through
  them so a rename can't drop a table from exports. A check whose settings
  live in a new per-page table adds its prefix to the registry.
  `RECORD_LEVEL_TABLE_PREFIXES` names the ones holding decisions about
  individual records.
- **Record-level decisions.** `export_project_config(...,
  include_record_level=False)` leaves out the corrections and the
  `RECORD_LEVEL_TABLE_PREFIXES` tables. The project card's **Export
  configuration** dialog (`views/start_view.py`) exposes this as a checkbox,
  ticked by default, and builds the bundle only once the dialog opens. Apply
  writes whatever the bundle holds; attribution rows for records that don't
  exist are kept but match nothing.
- **Pages.** Apply creates a page only when no page has its name and its
  survey dataset was imported. Only then are its settings file and check
  tables written, so an existing page keeps its own.
- **Missing codes.** Export reads `missing_codes_{project_id}`. Apply merges
  them into the target project's table by `label`: a bundled label replaces
  the local one, other local labels are kept.
- **Versions.** Export sets `bundle_version` (`BUNDLE_VERSION`). A bundle
  without it predates check tables and missing codes; it still applies, and
  the import dialog warns that those aren't included
  (`bundle_version_warning`). New fields default to empty, so older bundles
  parse. The retired per-page `missing_settings` is accepted when parsing
  but is neither exported nor written on apply.

## Session state

`app.py` initializes all cross-page session state. Key variables:
`st_project_id` (current project), `st_raw_dataset_list`,
`st_prep_dataset_list`, and page handles (`st_prep_data_page`,
`st_output_pages`, ...). View modules are page scripts: they run top to bottom
on every rerun and guard on `st_project_id`, calling `st.stop()` when no
project is selected. If cross-page state looks corrupted, check `app.py` first.

The check page last viewed is not session state: see
[View state](#view-state) ("Last viewed check page").

### URL state

The check page's selected check is the `check` URL query parameter, for
example `?check=duplicates`. Each generated check page is its own page, so the
parameter is per page. `nav_ui.resolve_selection` reads it on every run; a
valid value wins over the remembered and saved selections (see
[View state](#view-state)), and an invalid one opens the default
(Summary).
Changing the selection writes the parameter, so links and bookmarks open the
same check. To select a check from code (for example a button), call
`nav_ui.select_nav_item(key, "check", slug)`, ideally in an `on_click`
callback.

Navigation state lives under keys prefixed with the page's navigation key
(`check_nav_{page_name_id}__{project_id}` on check pages): `__selected`,
`__group`, `__item`, `__last_by_group` and `__errors`. Opening another project
keeps session state, so every navigation key includes the project ID
(`nav_ui.project_nav_key`). A remembered selection the items no longer offer
gives way to the saved one.

Prepare Data uses `?dataset=<alias>` (navigation key `prep_nav__{project_id}`)
and Corrections uses `?page=<page_name_id>` (navigation key
`corrections_nav__{project_id}`) in the same way. No other page uses query parameters.

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
