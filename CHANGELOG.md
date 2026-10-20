# TECHNICAL CHANGELOG

All notable changes to DataSure will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Check status** (#374): Every check has a cheap status that returns a
  `StatusResult` (ready, not set up, not applicable or error, with a reason)
  from page configuration and data shape only. Checks with their own
  conditions expose a status function (`duplicates_status`,
  `outliers_status`, `gpschecks_status`, `enumerator_status`,
  `backchecks_status`); Summary, Progress, Missing Values and Descriptive
  Stats share one row-count status in the catalogue (`rows_status`). GPS Checks is not applicable
  when no column looks like GPS data (`find_gps_columns`,
  `checks/gpschecks/compute.py`); Backchecks is not set up without a
  backcheck dataset
- **Shared navigation** (#374): `utils/navigation.py` is a pure resolver
  (`resolve_nav`, `group_selection`, `with_errors`, `nav_label`) and
  `utils/nav_ui.py` the Streamlit helper (`resolve_selection`, `draw_nav`,
  `select_nav_item`, `render_selected`, `run_guarded`, `guarded_status`),
  for reuse by Prepare Data and Corrections
- **Saved view state** (#375): `utils/view_state.py` keeps the last selected
  check and each check's filter, selection and sort widget values in a
  `view_state` section of the page settings file (`ViewState.bind`,
  `bind_widget`, `saved_selection`, `save_selection`). Saved values that no
  longer match the data are dropped. Each check gets a "Reset filters" action
  (`reset_filters_button`) that clears only its own view state. `ViewState`
  takes any settings file, for reuse by Prepare Data and Corrections
- **Summary check health grid** (#376): Under its tiles, Summary shows a card
  for every other catalogue check with its group, status (text and icon) and
  either a headline or the reason it is not ready. "Open →" (ready or error)
  and "Set up →" (not set up) select the check through `select_nav_item`, so
  `?check=` follows (`checks/health.py`: `health_cards`,
  `render_health_grid`)
  - Six checks expose a headline function, registered as
    `CheckEntry.headline`: `progress_headline` (share of target, or
    submissions), `missing_headline` (mean % of values missing),
    `duplicates_headline` (unresolved duplicate IDs after Records to
    Include), `outliers_headline` (total outliers and constraint violations,
    accepted flags left out), `enumerator_headline` (enumerators active in
    the past 7 days out of all) and `backchecks_headline` (total error rate).
    Descriptive Stats shows status only
  - Headlines run only for ready checks and are cached on the page's data,
    settings files, the logs and intermediate databases and the date; a
    headline that raises is shown on its card and not cached
  - `flagged_outlier_percent` and `outliers_headline` share one helper
    (`_reviewed_flags`); `database_path` (`utils/duckdb_utils.py`) returns a
    project database's file path; `CHECK_PARAM` and `check_nav_key` move to
    `checks/catalogue.py`

### Changed

- **Check page opens on the last viewed check** (#375): With no `?check=`
  URL parameter, a check page opens on the check last viewed on it, also in
  a new session. A valid URL parameter still wins
- **View state stays local** (#375): Project configuration exports leave out
  `view_state` (`without_view_state`), and applying a configuration keeps
  the local `view_state` and ignores any in the bundle
  (`utils/project_config.py`)
- **Check page navigation** (#374): The nine check tabs are replaced by a
  segmented control for the group (Overview, Data integrity, Field team,
  Exploration) and pills for that group's checks, with short labels
  (Progress, Enumerator Stats, Backchecks, Descriptive Stats). Only the
  selected check's report runs. The `check` URL query parameter reflects and
  drives the selection; Summary is the default
  (`render_checks`, `views/output_view_template.py`)
  - One catalogue lists every check (`CHECK_CATALOGUE`,
    `checks/catalogue.py`); `PageConfig` and `CheckData` move to
    `checks/context.py`
  - Checks that are not ready are muted with a text and icon marker and open
    to an empty state with the reason; not-set-up checks then show their
    settings
  - A check that raises shows an error state with the traceback and is marked
    in the navigation; the rest of the page keeps working
  - Onboarding and demo guidance describe the new navigation; the unused
    `CheckPage` enum is removed
- **Prepare Data navigation** (#377): The per-dataset tabs are replaced by one
  wrapping row of pills, and only the selected dataset's preparation UI
  renders (`render_dataset`, `views/prep_view.py`)
  - Every dataset's prep table is still seeded from raw on each page load
    (`seed_prep_from_raw`), so Configure Checks and the replication package
    see datasets never opened on Prepare Data
  - Datasets with no imported rows are muted with a reason
    (`dataset_status`); a status that raises marks only that dataset
    (`guarded_status`), and `render_dataset` takes the dataset's nav item
    instead of computing its status again
  - A "Reset filters" action above the selected dataset clears that
    dataset's view state
  - The `dataset` URL query parameter reflects and drives the selection,
    which is saved in the `view_state` of `prep_view_settings.json`
  - `prep_add_step` and `prep_remove_step` take the dataset and its step
    index as arguments instead of reading the page's loop variables
- **Corrections navigation** (#377): The per-check-page tabs are replaced by
  one wrapping row of pills, and only the selected check page's corrections
  render. Configuration is still loaded by the page's position in
  `check_config` (`render_selected_check_page`, `views/correction_view.py`)
  - The selection follows the `page` URL query parameter (the page's
    `page_name_id`), then the check page last viewed, also in an earlier
    session (`last_check_page` in `project_view_settings.json`, written by
    `render_checks` only when it changes; a URL value leaves it in place),
    then the selection saved in `correction_view_settings.json`, then the
    first page
  - Check pages with no survey KEY column or no imported survey data are
    muted with a reason (`check_page_status`)
  - The Survey data / Backcheck data selector (`choose_dataset`) and the
    Correction Log filters are saved in `view_state` per check page, with a
    Reset filters action
  - Onboarding text and the user guide describe both pages' pills

### Fixed

- **Summary, Progress and Missing Values filters are view state** (#373):
  Their filters, selections and time periods were saved with the check's
  settings, so they were exported, copied by templates and not cleared by
  Reset filters. They now bind to the check's `view_state` scope
  (`check_view` in `checks/summary.py`, `checks/progress.py`,
  `checks/missing.py`). An older settings file still loads: the values move
  from the check's settings into view state on first use
  (`ViewState.adopt_legacy`, `view_factory(..., legacy=...)`)
- **Not-applicable checks keep their settings** (#373): A not-applicable
  check shows its settings section under the empty state
  (`CheckEntry.settings`, `render_selected(settings=...)`;
  `outliers_settings_section`, `gpschecks_settings_section`,
  `backchecks_settings_section`). Backchecks' not-set-up message now points
  to the linked page instead of "Set it up below" (`CheckEntry.setup_hint`)
- **GPS Checks lockout** (#373): A saved GPS column configuration whose
  columns are in the data makes GPS Checks ready, whatever the columns are
  named, so the name heuristic no longer hides a configured check
  (`has_usable_gps_config`, `checks/gpschecks/compute.py`)
- **Check settings** (#374): The progress, duplicates, GPS and enumerator
  settings loaders no longer cache for 60 seconds, so a check opened again
  shows the settings saved a moment ago (`load_default_settings`,
  `load_default_duplicates_settings`, `load_default_gpschecks_settings`,
  `load_default_enumerator_settings`)

- **Summary tab data quality** (#358): The outlier % and back check error
  rate tiles show the values from the Outliers & Constraints and Backcheck
  Analysis tabs instead of always 0
  - Root cause: both tiles were placeholders fixed at 0 in
    `calculate_data_quality_metrics`
  - Solution: `flagged_outlier_percent` (checked, non-missing values flagged
    as outliers, leaving out accepted flags) and `overall_error_rate_percent`
    (the tab's total error rate) compute the values from the saved settings
    without rendering those tabs. With no outlier or backcheck columns
    configured, or no backcheck data, the tile says where to configure it
    instead of showing 0
  - `load_saved_backchecks_settings` also reads the comparison options (no
    differences, excluded values, string options), which the settings file
    stores under their widget names, so the Summary error rate matches the
    tab

## [1.2.0a2] - 2026-10-20

### Added

- **Replication package**: An **Exclude reviewer names** checkbox on the Export
  Replication Package page blanks the `user` column in the exported
  `correction_log.csv`. The column is kept so the schema matches
  `CORRECTION_LOG_SCHEMA`, and the project's stored log is not changed. Off by
  default; changing it discards an already-built package
  (`build_replication_package(exclude_reviewer_names=...)`,
  `src/datasure/views/replication_view.py`) — closes #332

### Changed

- **Dependencies**: `polars>=1.30.0,<3` (was `>=1.30.0`), lock moved from
  1.43.2 to 2.0.0. Every replacement below exists in polars 1.30.0, so the
  floor is unchanged; polars 3 is excluded until tested
- **Dependencies**: Relaxed the exact `streamlit==1.61.0` pin to
  `streamlit>=1.65.0,<2` (lock: Streamlit 1.66.0, Starlette 1.8.0). Only
  Streamlit major releases now need a deliberate bump (`pyproject.toml`) — #330

### Fixed

- **Zero-row prep and corrected data** (#315): A prep step or correction
  that removed every row no longer brings back raw data on check pages
  - Root cause: `load_data_with_fallback` and the Prep page could not tell a
    missing table from one with no rows
  - Solution: `load_data_with_fallback` uses the first table that exists
    (`duckdb_table_exists`). A new `TableState` (missing, no rows, has rows)
    replaces the ad hoc width and height checks. Check pages stop with a "no
    rows" message (`stop_if_no_survey_data`), or an "import it" message when
    the dataset was never imported. The Backcheck Analysis tab
    says when backcheck data has no rows. The Prep page keeps its step
    controls and Change Log when prep data has no rows, and the Correct Data
    page warns while keeping its Correction Log and remove control. Prep data
    with no rows seeds the corrected table, so Correct Data shows the dataset
    as emptied rather than missing.
    `compute_missing_columns`, `compute_average_interviews`,
    `compute_attempted_interviews` and `detect_outliers_with_clusters` accept
    zero-row input
  - Files: `src/datasure/utils/dataframe_utils.py`,
    `src/datasure/views/output_view_template.py`,
    `src/datasure/views/prep_view.py`, `src/datasure/views/correction_view.py`,
    `src/datasure/processing/corrections.py`,
    `src/datasure/checks/missing.py`, `src/datasure/checks/progress.py`,
    `src/datasure/checks/gpschecks/compute.py`
- **Demo guidance on non-demo projects** (#359): Renaming a report function
  that shows demo guidance no longer crashes its page in every project
  - Root cause: `demo_output_onboarding` read the message before checking
    `is_demo_project()`, and a missing entry came back as the string
    `"Invalid Message"`, so `.get` raised `AttributeError`
  - Solution: The message is read only in the demo project, and
    `OutputOnboardingInfo.get_onboarding_message` returns `None` for a
    missing entry, which shows no guidance and logs a warning. The decorator
    records each function in `DEMO_OUTPUT_FUNCTIONS`, and a test asserts
    every one has a message. The warning is logged once per function
  - Files: `src/datasure/utils/onboarding_utils.py`,
    `tests/utils/test_onboarding_utils.py`
- **Outliers & Constraints tab crashes** (#368): The tab no longer crashes
  with `ColumnNotFoundError: "action"` or `DuplicateError: 'index'`, and
  constraint checks no longer flood the terminal with polars warnings
  - Root cause: Reapplying corrections for an alias with no correction log
    saved a 0-row log of only `status` and `status_reason` (1.1.0 also did
    this on every re-import). `get_active_acceptances` and
    `get_active_corrections` then filtered on the missing `action` column.
    Deleting an outlier column saved the `index` helper column into
    `outliers_<page>`, which `with_row_index()` then added again. Constraint
    checks built `pl.col(col) < None` for every unset bound
  - Solution: Reapplying with no log saves the corrected data and writes no
    log. `ensure_log_columns` reads a log with no `action` column as no log,
    so projects that already hold one recover. Deleting an outlier column
    numbers its rows in a `row_nr` column and saves only the settings
    columns. Loading the outlier settings drops an `index` column saved by
    earlier versions, and the next render saves the cleaned settings.
    Constraint checks add a branch only for the bounds that are set
  - Files: `src/datasure/processing/correction_log.py`,
    `src/datasure/processing/corrections.py`,
    `src/datasure/checks/outliers/report_ui.py`,
    `src/datasure/checks/outliers/compute.py`
- **Polars 2.0 compatibility**: The Prep page and several checks crashed on
  fresh installs that resolved polars 2.0
  - Root cause: polars 2.0 removed `NUMERIC_DTYPES`, `INTEGER_DTYPES`,
    `DATETIME_DTYPES`, `with_row_count`, `pl.count()` and String-to-Date
    `cast`
  - Solution: use `cs.numeric()`, `dtype.is_numeric()`,
    `dtype.is_integer()`, `isinstance(dtype, pl.Datetime)`,
    `with_row_index`, `pl.len()` and, for String columns,
    `str.to_date("%Y-%m-%d", strict=False)` (`_to_date_expr`)
  - Files: `src/datasure/utils/dataframe_utils.py`,
    `src/datasure/checks/duplicates.py`, `src/datasure/checks/missing.py`,
    `src/datasure/checks/summary.py`, `src/datasure/checks/outliers/compute.py`,
    `src/datasure/checks/enumerator/report_ui.py`,
    `src/datasure/processing/prep.py`
- **Integer columns**: `get_df_columns` listed only signed `Int8`–`Int64`
  columns as integer columns for polars data, missing unsigned and `Int128`
  columns; it now uses `cs.integer()` (`src/datasure/utils/dataframe_utils.py`)
- **Server**: Fresh installs disconnected after the UI loaded, with
  `RuntimeError: Expected ASGI message 'http.response.start', but got
  'http.response.body'` on image and video responses. Starlette 1.8.0 changed
  `IdentityResponder.send_with_compression`, which Streamlit 1.61.0's gzip
  middleware overrides; Streamlit 1.62+ is compatible — closes #330
- **SurveyCTO import**: Submissions completed before 2024-01-01 were never
  downloaded. `SurveyCTOConfig.default_date` is now 2010-01-01 UTC. It is not
  `date=0`, which SurveyCTO throttles to one request per licensed quiet period
  (HTTP 417) (`src/datasure/connectors/scto.py`) — closes #341
- **Start page**: "Learn more" listed SPSS as a supported local file format; it
  now lists CSV, Excel, Stata, JSON and Parquet
  (`src/datasure/views/start_view.py`)
- **Local import**: Legacy `.xls` files passed the file-type check and then
  failed with an openpyxl error, because openpyxl cannot read `.xls`. They are
  now rejected up front, in the form and in `FileConfig`, with an instruction to
  save the file as `.xlsx`; README, User Guide and Architecture no longer list
  `.xls` (`src/datasure/connectors/local.py`)
- **Correction replay**: Replay silently overwrote a value fixed at source when
  the corrected value was originally missing. `_current_value_mismatch` no
  longer skips a missing recorded value, so the correction applies only while
  the cell is still missing and otherwise fails with a reason; the same check
  runs when a correction is first applied
  (`src/datasure/processing/corrections.py`) — #337
- **Acceptance status**: An accept row's Status in the Correction Log was
  judged against the data at that point in replay, so an accept followed by a
  modify of the same cell showed `Successful` while the check pages treated it
  as inactive. Accept statuses are now judged against the final corrected data,
  as `get_active_acceptances` does, on replay and on every log save — closes #337
- **Correction KEY lookup**: Replay and acceptance statuses found a record by
  the first column holding its KEY value, so a value repeated in another column
  could point them at the wrong record and mark an active acceptance
  `Inactive`. They now use the KEY column the check config sets for the
  dataset (the survey or backcheck KEY), falling back to the old lookup only
  when none is set (`src/datasure/processing/corrections.py`) — #337
- **Remove Credentials**: Reported success but left the SurveyCTO password in
  the OS keyring. The view passed the credential type as the server, and
  `delete_stored_credentials` read the username from the wrong level of the
  metadata file, so `keyring.delete_password` never ran. A keyring failure now
  returns an error, shown with `st.error`; a password already missing from the
  keyring still clears the entry (`src/datasure/utils/secure_credentials.py`,
  `src/datasure/views/import_view.py`) — closes #342

## [1.2.0a1] - 2026-10-11

### Added

- **Correction log**: New `source` column records which page made each entry;
  existing logs load with `source = corrections_page`. A new `check_type`
  column goes with the new `accept` action
  (`CORRECTION_LOG_SCHEMA`, `ensure_log_columns` in the new Streamlit-free
  `src/datasure/processing/correction_log.py`, shared with the replication
  package, which now exports legacy logs with these columns) — #296
- **Accept action**: `CorrectionProcessor.accept_value` records that a flagged
  value (outliers, constraints, GPS) was reviewed and
  is correct, with a required reason. An acceptance is rejected if the data
  no longer holds the value being accepted. `get_active_acceptances` returns the
  acceptances whose recorded value still matches the data (for GPS, both
  latitude and longitude). Replay never changes data for `accept` rows, but
  marks an acceptance whose value no longer matches the data with status
  `Inactive` (not a reapply failure). The generated `4_corrections.do` skips
  `accept` rows; `correction_log.csv` keeps them, and the README's correction
  counts exclude them. Values compare by value, not text: missing matches
  missing (None or NaN), values that both read as numbers compare numerically
  (a String cell `"25"` matches `25.0`), and every row with the KEY must
  match — #296
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
- **Duplicate card corrections**: Each duplicate ID card has a Keep / Modify
  ID / Drop choice per record, and each unmatched backcheck card a Modify ID /
  Drop choice, with one required reason and note and one Save. A save logs one
  entry per changed record ("modify value" on the ID column or "remove row",
  source `duplicates`) to the survey or backcheck alias's log, through the
  atomic `apply_corrections`. Save is disabled, with the reasons listed, until
  at most one record keeps the ID and every new ID is non-empty, changed,
  distinct within the save, valid for the ID column's type and not held by an
  included record (naming its KEY); an unmatched backcheck's new ID must be a
  survey ID. Dropping every record goes through `confirm_dialog`. Records
  sharing a KEY can't be corrected on a card. A caption above the cards counts
  the corrections logged this session and links to the Correction Log, where
  they are undone. Decision logic is in the new Streamlit-free
  `checks/id_corrections.py`; `IdView` gains `alias`, `processor` and
  `resolved`, and `duplicates_report` takes the survey `alias` — #303
- **Corrections page dataset switcher**: Pages with backcheck data get a
  Survey data / Backcheck data switcher on their Correct Data tab. On backcheck
  data, the add form offers only "modify value" on the backcheck ID column and
  "remove row" (`correction_datasets`, `CorrectionDataset`); the log, removal
  and preview use the backcheck alias. The backcheck KEY and ID columns come
  from the Backcheck Analysis tab (`backchecks.models.backcheck_id_columns`,
  read from `settings_utils.page_settings_file`) — #303
- **Backcheck comparison scope**: The comparison and coverage use the
  Duplicates tab's survey and backcheck Records to Include filters (new
  `checks/backchecks/scope.py`, `duplicates.saved_records_to_include`,
  `describe_records_to_include`). The page states the active filters and
  counts, and a warning above Comparison Results Details counts the duplicate
  survey IDs, duplicate backcheck IDs and unmatched backcheck IDs left out —
  #303
- **GPS outlier corrections**: Each row of the GPS outliers table has a Review
  button that opens the correction form in a dialog, prefilled from the KEY and
  the configured latitude and longitude, to modify coordinates, remove
  coordinates, remove the observation or accept the location (source and check
  type `gps`). Coordinate changes write one log entry per coordinate column
  with a shared reason through `CorrectionProcessor.apply_corrections`, so both
  apply or neither does; removing coordinates clears only the latitude and
  longitude columns. Acceptances are (`gps`, KEY, no column), record both
  coordinates and lapse if either changes. Accepted outliers are hidden from
  the table and the outlier count unless "Show reviewed" is on, and are drawn
  green on the map. A single-column GPS configuration, or one that uses the
  same column for latitude and longitude (now rejected by the settings schema),
  offers only "remove observation". Review is blocked for a KEY on several rows
  with different coordinates, and turned off with a warning for a Survey KEY
  named "review status" or "review reason". Logic is in the new Streamlit-free
  `checks/gpschecks/review.py` — #304
- **Correction Log filters**: Source and Action `st.pills` (multi-select)
  above the Correction Log on the Correct Data page, offering only the values
  present in the log. An empty selection doesn't filter; the two combine.
  Filtering is `correction_view.filter_correction_log`; the removal form still
  lists every entry — #305

### Changed

- **Breaking**: `_filter_data_on_conditions`, which saved the filtered rows to
  the project-wide DuckDB table `filtered_duplicates_data`, is replaced by
  `apply_records_to_include(data, conditions)`, which returns them. The Records
  to Include filter applies as soon as it has a value (the Apply Filter button
  is gone), and its condition column is restored from the page settings.
  `duplicates_report` and `duplicates_report_settings` take an optional
  `backcheck_data` — #306
- **Breaking**: `duplicates` is no longer in `ACCEPT_CHECK_TYPES`: an ID
  belongs to one record, so a duplicate ID is resolved on its card, not
  accepted — #303
- **Breaking**: The backcheck `drop_duplicates_option` setting (Duplicate
  Handling) is removed. Records whose survey ID is duplicated among the
  included records are always left out of the comparison and coverage
  (`compute.exclude_duplicate_ids` replaces `_prepare_data_for_merge`), and
  come back once resolved. Pages that saved "first" or "last" now exclude
  duplicates; the saved value is ignored — #303
- `duplicates._FilteredRecords`, `_records_to_include` and
  `_render_filter_messages` are now public as `FilteredRecords`,
  `filter_records_to_include` and `render_filter_messages` — #303
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

- **Resolved metric**: The Resolved metric on the ID duplicate cards was
  always 0. It now counts the duplicate IDs, among the included records, that
  corrections from any page have resolved (`id_duplicates.count_resolved_ids`)
  — #303
- **Raw fallback**: `CorrectionProcessor.get_corrected_data` and
  `_reapply_all_corrections` seeded only from `prep`, so an alias with no prep
  table, such as unprepared backcheck data, could not be corrected. They now
  fall back to `raw` (`get_uncorrected_data`) — #303
- **Duplicates filter**: Pages in one project shared the Records to Include
  filter through `filtered_duplicates_data`, so one page's filter overwrote
  another's. Each page now applies its own saved conditions — #306
- **Duplicates filter**: A filter that matched no records silently checked
  every record. It now shows a warning and checks no records — #306
- **Duplicates filter**: A saved single-value filter (string or numeric), or a
  numeric includes/excludes filter, came back empty in a new session and was
  then saved as empty, dropping the filter. Saved values are now restored, and
  saved values no longer in the data are dropped instead of failing — #306
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
- **Stale corrections**: `apply_corrections` now rejects a "modify value" or
  "remove value" entry whose `current_value` doesn't match the data, as it
  already did for acceptances. Replay (`_current_value_mismatch`) compares the
  recorded value by value instead of by `str()`, so a correction saved with a
  prefilled `25.0` against an integer `25` is no longer reverted on the next
  refresh — #296
- **Correct Data page**: Apply now saves through the shared form's
  `apply_correction_entries` (`apply_corrections`) instead of
  `CorrectionProcessor.apply_correction`, so it gets the same stale-value
  check and all-or-nothing save as the check pages. `_handle_apply_correction`
  is removed — #296
- **Constraint violations**: A value past a hard bound was reported as a soft
  violation whenever a soft bound on the same side was set (for example,
  above the hard maximum read "above soft maximum"), so hard violations were
  undercounted. Hard bounds are now tested first
  (`compute_constraint_violations`) — #298
- **Mapbox token**: Saving the token from the GPS settings never persisted it:
  `save_secrets` returned early unless a session-state flag nobody set was
  true. The token is now kept in the OS keyring, shared by every project on
  the machine, with `secrets.toml` read as a fallback; the plain-text
  `settings_utils.save_secrets` is removed — #304
- **GPS acceptances on integer KEYs**: An integer KEY column with nulls came
  back from `to_pandas` as floats, so KEY `1` read as `1.0` and never matched
  its acceptance. Integral float KEYs are converted back to ints before
  matching and prefilling the form — #304

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
