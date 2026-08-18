# TECHNICAL CHANGELOG

All notable changes to DataSure will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
- **Duplicates check**: Clarified filter settings copy on the duplicates
  check page (`src/datasure/checks/duplicates.py`) — #273

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
