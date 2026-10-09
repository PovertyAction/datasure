# TECHNICAL CHANGELOG

All notable changes to DataSure will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Correction log**: New `source` column records which page made each entry;
  existing logs load with `source = corrections_page`. A new `check_type`
  column goes with the new `accept` action
  (`CORRECTION_LOG_SCHEMA`, `ensure_log_columns` in the new Streamlit-free
  `src/datasure/processing/correction_log.py`, shared with the replication
  package, which now exports legacy logs with these columns) — #296
- **Accept action**: `CorrectionProcessor.accept_value` records that a flagged
  value (outliers, constraints, duplicates, GPS) was reviewed and
  is correct, with a required reason. An acceptance is rejected if the data
  no longer holds the value being accepted. `get_active_acceptances` returns the
  acceptances whose recorded value still matches the data (for GPS, both
  latitude and longitude). Replay and the generated `4_corrections.do` skip
  `accept` rows; `correction_log.csv` keeps them, and the README's correction
  counts exclude them. Values compare by value, not text: missing matches
  missing (None or NaN), numbers compare numerically, and every row with the
  KEY must match — #296
- **Atomic apply**: `CorrectionProcessor.apply_corrections` applies a list of
  `CorrectionEntry` objects all or nothing; if the log save fails, the
  corrected data is restored — #296
- **Shared correction form**: `src/datasure/utils/correction_form.py`
  (`render_correction_form`, `render_correction_inputs`,
  `apply_correction_entries`) renders the action, new-value and reason inputs
  for a prefilled KEY/column/current value, with namespaced widget keys. The
  Correct Data page now uses it — #296
- **Outliers and constraints corrections**: Each row of the constraint
  violations and outlier inspection tables has a Review button (a pinned
  `st.column_config.ButtonColumn`) that opens the shared correction form in a
  dialog, prefilled with the row's KEY, column and current value, to modify the
  value, remove it or accept it as valid (source and check type
  `outliers`/`constraints`). Accepted flags are hidden and left out of the
  metrics unless "Show reviewed" is on (then they are highlighted green), and
  come back if the value changes or
  the acceptance is removed. Accepting a hard violation needs a confirmation.
  A "Show only flagged values" toggle (on by default) sits above both tables;
  the outlier inspection table previously always listed unflagged values too.
  With "Show reviewed" on, values whose current value comes from a modify or
  remove correction are also highlighted green, with a "Corrected" badge and
  the correction reason (new `CorrectionProcessor.get_active_corrections`);
  unlike accepted flags, corrected values that are still flagged stay visible
  and counted. A "Show only reviewed" toggle lists only accepted and
  corrected rows and disables the other two toggles while on (toggle values
  are a `review.TableFilters`, applied by `review.filter_table`). The outlier
  inspection table now hides its index. Styled tables
  are built with new `ui_utils.row_styler`, which keeps values displayed as in
  the unstyled table (pandas' default Styler formatting showed `150` as
  `150.000000` and missing values as `nan`).
  Flag review logic lives in the new Streamlit-free
  `src/datasure/checks/outliers/review.py`; `outliers_report` takes the
  dataset `alias`. Removed the unused `_render_outlier_table`.
  `queue_notice` gains a `toast` level, and `show_queued_notices` returns
  whether it showed anything. New `ui_utils.ensure_styler_limit` raises
  pandas' process-wide `styler.render.max_elements` under a lock and never
  lowers it, so concurrent sessions can't cut it below what another render
  needs; it replaces the `pd.set_option` calls in the summary, missing and
  progress checks, which lowered the limit to fit their own tables and could
  crash other styled tables. New `ui_utils.styled_dataframe` renders a Styler
  after raising the limit to fit it; the results tables and the Correction
  Log use it. A soft-violation acceptance no longer hides a value that has
  since become a hard violation (e.g. after bounds are tightened): it needs a
  new hard acceptance. A correction that failed to reapply to new prep data
  is never shown as Corrected, even if the data holds its new value. Review
  on a KEY whose rows hold different values of the column shows a warning
  instead of the form, since a correction changes every row with the KEY
  (`review.key_has_conflicting_values`). Survey fields added through "Show
  more columns" that share a name with a results or review column get a
  " (survey)" suffix, even while the review columns are hidden. A Survey KEY
  named "review status" or "review reason" turns review off with a warning
  instead of being overwritten — #298
- **Correction log severity**: New `severity` column, `hard` on acceptances of
  hard constraint violations (null otherwise and for legacy logs).
  `CorrectionEntry.severity` sets it and is rejected on non-accept actions,
  on acceptances of other checks, and with any value other than `hard`.
  Hard acceptances are highlighted in the Correction Log — #298
- **Backcheck targets**: New `checks/backchecks/coverage.py`.
  `compute_backcheck_coverage` returns `BackcheckCoverage`: eligible unique
  survey IDs (after duplicate handling and the optional eligibility filter),
  how many have a matching backcheck, the on-track %, points vs the target, and
  expected backchecks, `ceil(survey_target × target% / 100)`, when
  `survey_target` is set. `compute_staff_coverage` returns per-enumerator
  coverage, including enumerators with no backchecks, or backchecks done per
  backchecker. Neither needs comparison columns. The Backchecks Summary has a
  new Targets section showing coverage against the target % and backchecks
  done against expected, each with its deviation as a delta. The settings
  panel gains an eligibility filter (`eligibility_column`,
  `eligibility_values`).
  `settings_from_page_config` builds `BackcheckSettings` from the page config,
  where a target of 0 means not set — #318
- **Correction log user**: New `user` column records who made each entry,
  from any source. `get_reviewer_name()` in the new
  `src/datasure/utils/reviewer.py` returns the "Reviewer name" set in the
  sidebar, saved in `cache/user_settings.json`, else the OS login
  (`getpass.getuser()`). Existing logs load with a null `user`. The
  Correction Log table and `correction_log.csv` include it — #321
- **Backcheck mismatch attribution**: New Streamlit-free
  `checks/backchecks/attribution.py`. Reviewers attribute mismatches in
  Comparison Results Details to an `ErrorSource` (Enumerator, Backchecker,
  Respondent, Unattributed) from a pinned Review button that opens a dialog;
  selecting several mismatch rows and clicking Review on one of them
  attributes them together. Only `match_status == "mismatch"` rows can be
  attributed, and Backchecker and Respondent need a note. Entries are appended
  to `bc_attribution_{page_name_id}` in the `logs` db with the survey and
  backcheck KEYs, column, both values (as text), source, note, user
  (`get_reviewer_name`) and date. `mark_error_sources` adds an `error_source`
  column: the latest entry per KEY pair and column applies only while both
  values still equal the stored ones, otherwise the mismatch is Unattributed.
  An Attribution log expander lists the history. Attribution never changes
  the data, the mismatch counts or the regular error rate — #301
- **Adjusted error rate**: `compute_enumerator_backchecker_stats` adds
  "Adjusted Error Rate % (Cat n)" and "(Total)": for enumerators
  (mismatches − Backchecker − Respondent) ÷ values compared, for backcheckers
  (mismatches − Enumerator − Respondent) ÷ values compared. Unattributed
  mismatches always count. `compute_column_stats` adds "Enumerator / Backchecker
  / Respondent / Unattributed Mismatches" counts. The Backchecks Summary shows
  "Mismatches Attributed" (% of mismatches with a source). New optional
  `BackcheckSettings.error_rate_target_percent` ("Error rate target (%)" in
  Tracking Options): each regular and adjusted rate column above it is
  highlighted in both the enumerator and backchecker views — #301
- **Overall backcheck error rates**: `compute_overall_error_rates` returns an
  `OverallErrorRate` (compared, mismatches, error rate, enumerator and
  backchecker adjusted rates) for the total over categories 1–3 and for each
  category. The Backchecks Summary gains an Error Rates section below Targets
  with one card each, the enumerator adjusted rate as a grey, arrowless delta
  and the backchecker adjusted rate in the help — #301
- **ID duplicate cards**: The ID Duplicates section shows one card per
  duplicate ID instead of a flat table. Each card compares the records side by
  side (fields as rows, records as columns), highlights fields that differ, and
  has "Compare all fields" and "Only differing fields" toggles. Metrics,
  search by ID or KEY, sort by group size or latest date, 10 cards per page and
  a "Download duplicates (CSV)" export sit above the cards. Pages with backcheck
  data get a Survey data / Backcheck data switcher; the backcheck view also
  lists unmatched backcheck IDs and has its own Records to Include filter,
  saved under `backcheck_`-prefixed keys. Logic is in the new Streamlit-free
  `checks/id_duplicates.py`, rendering in `checks/id_duplicates_ui.py`;
  `DuplicatesSettings` gains `team` and `backcheck_conditions` — #306

### Changed

- **Breaking**: `_filter_data_on_conditions`, which saved the filtered rows to
  the project-wide DuckDB table `filtered_duplicates_data`, is replaced by
  `apply_records_to_include(data, conditions)`, which returns them. The Records
  to Include filter applies as soon as it has a value (the Apply Filter button
  is gone), and its condition column is restored from the page settings.
  `duplicates_report` and `duplicates_report_settings` take an optional
  `backcheck_data` — #306

- **Breaking**: `backchecks` is no longer in `ACCEPT_CHECK_TYPES`, so a
  backcheck mismatch can't be accepted; it can only be attributed — #301

- **Breaking**: `BackcheckSettings.backcheck_target_percent` is now
  `float | None` (0–100), defaulting to None instead of 10;
  `effective_target_percent` applies the 10% default. The target resolves from
  the settings panel, then the page config, then 10%. A cleared panel value, or
  a saved value outside 0–100, falls back to the page config.
  `BackcheckSettings` gains `survey_target` — #318
- **Breaking**: `compute_enumerator_backchecker_stats` no longer returns the
  "Surveys" and "Backchecks" columns (both were the count of compared survey
  KEYs). The Enumerator Backchecker Error Statistics table now takes them from
  `compute_staff_coverage` and renders before comparison columns are
  configured — #318

### Fixed

- **Duplicates filter**: Pages in one project shared the Records to Include
  filter through `filtered_duplicates_data`, so one page's filter overwrote
  another's. Each page now applies its own saved conditions — #306
- **Duplicates filter**: A filter that matched no records silently checked
  every record. It now shows a warning and checks no records — #306
- **ID duplicates**: `compute_id_duplicates` added a stray null column when no
  date column was configured, and failed when the configured date (or KEY)
  column was missing from the data. Both are now skipped — #306
- **Corrections cache**: `CorrectionProcessor`'s cached reads were keyed only on
  `alias`, so two projects sharing an alias shared cached corrected data and
  logs. The processor is now hashed by `project_id` — #296
- **Apply button**: A new value of `0` no longer disables Apply. An empty
  string still does; use "remove value" to blank a cell — #296
- **Backcheck settings**: `backchecks_report_settings` passed the duplicate
  option and target as `drop_duplicates` and `backcheck_goal`, which
  `BackcheckSettings` silently dropped, so duplicates were always dropped and
  the target was always 10. They are now passed as `drop_duplicates_option`
  and `backcheck_target_percent`, and the target is saved under
  `backcheck_target_percent` so it reloads in later sessions. Targets saved
  under the old `backcheck_goal` key were never applied and are ignored — #299
- **Backcheck dates**: `_add_date_columns` joined backcheck dates on the survey
  KEY, so when survey and backcheck KEYs differed the dates and the "Avg Days"
  statistics were empty. Backcheck dates now join on the backcheck KEY
  (`{survey_key}__BCCL`). Backchecker statistics were also always empty when
  the survey KEY was the merge ID; they are now computed — #300
- **Correction log schema**: Removing the last correction entry now leaves an
  empty log with the full schema, including status columns — #296
- **Constraint violations**: A value past a hard bound was reported as a soft
  violation whenever a soft bound on the same side was set (for example,
  above the hard maximum read "above soft maximum"), so hard violations were
  undercounted. Hard bounds are now tested first
  (`compute_constraint_violations`) — #298

## [1.1.0] - 2026-09-21

### Added

- **Local file connector**: Added Parquet file format support for local file
  imports (`src/datasure/connectors/local.py`) — #245
- **Correction log**: Survey ID now shown on the Correct Data page and in the
  Correction Log, alongside correction status and status reason
  (`src/datasure/processing/corrections.py`,
  `src/datasure/views/correction_view.py`) — #264
- **Project creation**: Newly created projects are now automatically loaded
  and selected after creation, instead of requiring a manual return to
  project selection (`src/datasure/views/start_view.py`) — #272
- **Project configuration export/import**: A project's import sources, prep
  steps, HFC configs, and corrections can now be bundled into one portable
  JSON file and applied to a new or existing project, so a teammate (or a
  similar project) can start from an existing setup instead of configuring
  from scratch. Credentials, machine-specific file paths, and survey data
  are never included; applying a bundle replays the same pipeline a person
  would run by hand, skipping and reporting anything that can't apply
  rather than aborting the whole bundle
  (`src/datasure/models/schemas.py`, `src/datasure/utils/project_config.py`,
  `src/datasure/views/start_view.py`) — closes #251

### Changed

- **Outliers module**: Split the monolithic `src/datasure/checks/outliers.py`
  into a subpackage (`compute.py`, `models.py`, `report_ui.py`,
  `settings_ui.py`) for maintainability — #268, closes #197
- **View UI consistency**: Introduced shared header/section/dialog helpers
  (`src/datasure/utils/ui_utils.py`) and adopted them across `config_view.py`,
  `correction_view.py`, `import_view.py`, `output_view_template.py`,
  `prep_view.py`, `replication_view.py`, and `start_view.py` so page chrome
  (headers, section titles, metric rows, confirm dialogs) stays consistent as
  new views are added — #244
- **Dependencies**: `streamlit` pinned to an exact `==1.61.0` (previously
  `>=1.52.0`) for reproducible builds; `uv_build` upper bound raised to
  `<0.13.0`
- **Dev tooling**: Vendored Streamlit's official `developing-with-streamlit`
  meta-skill into `.claude/skills/` so it is available to every contributor
  without a user-level install; trimmed the project-local `streamlit` skill
  down to DataSure-specific patterns (asset paths, cache directory
  resolution) — #274
- **CI**: Bumped `actions/checkout` to 7.0.1, `actions/setup-python` to
  7.0.0, `astral-sh/setup-uv` to 8.3.2, and `SonarSource/sonarqube-scan-action`
  to 8.2.0 — #255, #257, #243, #236, #235
- **CI**: Bumped `astral-sh/setup-uv` to 10.0.1 (from 8.3.2) — #280
- **Duplicates check**: Clarified filter settings copy on the duplicates
  check page (`src/datasure/checks/duplicates.py`) — #273
- **Project picker**: Replaced the Start page's single dropdown (which
  mixed real projects, the demo, and "Create New Project" as if they were
  the same kind of choice) with a searchable, sortable list — one row per
  project with an "Open" button and a "More" menu for the less-frequent
  export/update/delete actions, plus a dedicated "+ New Project" dialog
  (`src/datasure/views/start_view.py`)
- **Prep confirmation messages**: Row/column-removal, transform, and
  add-column confirmation messages now consistently end with "Dataset now
  has N rows and M columns" via new `PrepActionResult.remaining_rows`/
  `remaining_columns` fields, and remove-rows messages state the actual
  column, condition, and value instead of just the method label
  (`src/datasure/utils/prep_utils.py`, `src/datasure/processing/prep.py`)
  — #283

### Fixed

- **Prep "remove rows"**: Equal-to/not-equal-to filter conditions were
  inverted (matching rows were removed instead of kept, and vice versa);
  logic corrected (`src/datasure/processing/prep.py`) — #263
- **Datetime parsing**: Fixed parsing of datetime formats with missing
  seconds during data preparation (`src/datasure/processing/prep.py`,
  `src/datasure/views/prep_view.py`)
- **Bulk reapply error handling**: Prep reapply-all no longer crashes the
  page on a failing step (e.g. a re-import that drops a column an earlier
  step used); correction reapply-all no longer silently swallows failures.
  Both now collect per-item failures, skip just the failing item, and
  surface one shared warning at the UI boundary
  (`src/datasure/processing/prep.py`, `src/datasure/processing/corrections.py`,
  `src/datasure/utils/reapply_utils.py`) — closes #253
- **Stale prep/corrected data**: Re-importing raw data now properly
  invalidates stale prepared and corrected data instead of leaving outdated
  results visible (`src/datasure/processing/corrections.py`,
  `src/datasure/views/import_view.py`) — #254, closes #252
- **Release tooling**: Fixed the Windows `just` recipes for `tag-version`,
  `push-tag`, `push-all`, and `bump-and-tag` reporting a tag already existed
  for tags that were never created — PowerShell's `if()` was evaluating
  `git rev-parse`'s leftover stdout instead of its exit code (`justfile`)
  — #279
- **CLI**: `uv run datasure` now opens the default browser automatically on
  launch, matching `just datasure-dev` — a leftover `--server.headless true`
  flag (from an old PyInstaller-packaged build) was silently overriding
  `headless = false` already set in `src/datasure/.streamlit/config.toml`
  (`src/datasure/cli.py`) — #284

---

## [1.0.0] - 2026-07-10

### Added

- **Data quality checks**: Nine built-in check modules covering the full
  survey data quality workflow: `summary`, `missing`, `duplicates`,
  `gpschecks`, `outliers`, `enumerator`, `progress`, `descriptive`, and
  `backchecks` (`src/datasure/checks/`)
- **SurveyCTO connector**: REST API connector with basic auth, incremental
  data refresh, and encrypted attachment support via OS-stored private key
  (`src/datasure/connectors/scto.py`, `src/datasure/utils/scto_api.py`)
- **Local file connector**: Import from CSV, Excel (.xlsx/.xls), JSON, and
  Stata DTA formats (`src/datasure/connectors/local.py`)
- **Replication package export**: Generates portable Python and Stata scripts
  that reproduce the complete data pipeline outside DataSure, including
  codebook and README generation (`src/datasure/replication/`) — #165
- **Data preparation**: Polars-based preparation module with all operations
  recorded in a reproducible prep log for auditability
  (`src/datasure/processing/prep.py`)
- **Data corrections**: Workflow for applying targeted value and row
  modifications to survey data (`src/datasure/processing/corrections.py`,
  `src/datasure/views/correction_view.py`)
- **Per-project DuckDB storage**: Separate `raw.duckdb`, `prep.duckdb`,
  `corrected.duckdb`, and `logs.duckdb` databases per UUID-keyed project;
  platform-appropriate cache directories resolved automatically
  (`src/datasure/utils/duckdb_utils.py`, `src/datasure/utils/cache_utils.py`)
- **OS keyring credential storage**: SurveyCTO passwords stored in the OS
  keyring — no plaintext credentials written to disk or session state
  (`src/datasure/utils/secure_credentials.py`)
- **Dynamic report pages**: `ConfigurationService` generates
  `output_view_{N}.py` page scripts at runtime from a shared template,
  enabling per-project configurable report layouts
  (`src/datasure/utils/config_utils.py`, `src/datasure/views/output_view_template.py`)
- **CLI entry point**: `datasure` command launches the Streamlit application
  with optional custom port support (`src/datasure/cli.py`)
- **Demo/onboarding project**: Bundled sample data and guided onboarding flow
  for first-time users (`src/datasure/utils/onboarding_utils.py`,
  `src/datasure/assets/`)
- **Pydantic v2 schema validation**: All check settings, data models, and
  filter conditions validated via Pydantic v2 models
  (`src/datasure/models/schemas.py`, `src/datasure/models/enums.py`)
- **Multi-project support**: UUID-keyed project registry with per-project
  settings, credentials metadata, and isolated data storage
  (`cache/projects.json`)
- **SECURITY.md**: Vulnerability disclosure policy and reporting process — #206
- **CODE_OF_CONDUCT**: Community conduct guidelines — #211

### Changed

- **Build backend**: Migrated from setuptools to `uv_build`; package
  management and virtual environment handled exclusively via uv
- **Logo and layout**: Application logo revised and layout updated; footer
  enhanced with link to documentation and GitHub issue reporting — #221
- **Chart utilities**: `donut_chart2` consolidated into `donut_chart`,
  removing the duplicate implementation (`src/datasure/utils/chart_utils.py`)
  — #212
- **CLI version display**: Hardcoded version fallback string replaced with
  `"unknown"` to avoid displaying stale values (`src/datasure/cli.py`) — #214

### Fixed

- **Custom port URL**: Application URL displayed in the terminal after launch
  now reflects the correct address when a custom port is configured
  (`src/datasure/cli.py`) — #222
- **Exception handling**: Broad `except Exception` handlers narrowed to
  specific exception types throughout library code; bare-except linting
  re-enabled — #202
- **Logging**: `print()` statements in library code replaced with structured
  `logging` calls — #203
- **DuckDB SQL safety**: Table name validation hardened; user-supplied values
  in SQL are parameterised rather than f-string interpolated
  (`src/datasure/utils/duckdb_utils.py`)
- **Windows test stability**: Pytest `INTERNALERROR` caused by unrestored
  `os.name`/`pathlib` patches in tests resolved across the test suite — #207
- **Replication package install**: Incorrect `ipaclean` install path in
  generated scripts fixed — #174
- **Encrypted attachments**: Attachment downloads now work correctly when a
  private key is configured in the SurveyCTO connector — #179, #227
- **Filter coercion**: `_coerce_numeric_value` now raises `ValueError` for
  list inputs containing non-numeric strings instead of silently returning
  the original values unchanged; coercion errors in `_filter_data_on_conditions`
  are consistently wrapped as `"Error applying filter"` — #231
- **Polars compatibility**: Removed `polars<1.33.0` ceiling; replaced
  `str.to_decimal()` two-step cast with direct `cast(Float64, strict=False)`
  in `src/datasure/utils/dataframe_utils.py` — #231

### Security

- **Secret scanning**: Gitleaks pre-commit hook added to block accidental
  secret commits to the repository — #209
- **Dependency security floors**: Version minimums set for `pyarrow`,
  `starlette`, `tornado`, `h11`, `urllib3`, `gitpython`, `cryptography`,
  `setuptools`, and `pillow` to address Dependabot vulnerability alerts
  — #205
- **GitHub Actions hardening**: Workflow action versions pinned and
  permissions scoped; release pipeline hardened against supply-chain
  attacks — #234

### Dependencies

Key runtime dependencies introduced in this release:

- `streamlit>=1.52.0` — web application framework
- `polars>=1.30.0` — primary DataFrame library for data preparation and checks (no upper bound)
- `pandas>=2.2.2,<3.0` — interop layer for checks and DuckDB output
- `duckdb>=1.3.1` — per-project data storage
- `pydantic>=2.11.7` — schema validation for settings and data models
- `keyring>=25.6.0` — OS keyring credential storage
- `polars-readstat>=0.5.1` — Stata DTA file import
- `plotly>=6.2.0` — interactive charts and maps
- `pyarrow>=23.0.1` — Streamlit/Polars/pandas interop

---

*For guidance on maintaining this changelog, see [docs/changelog_guide.md](docs/changelog_guide.md)*
