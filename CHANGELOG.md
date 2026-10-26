# TECHNICAL CHANGELOG

All notable changes to DataSure will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Prep concat** (#388): Add Column has a `concat` method
  (`PrepFunctions.concat`) that joins two or more text columns in selection
  order with a separator stored in the step's `value` (`""`, `" "`, `","`,
  `"_"`, `"-"` or custom text; a null `value` means none).
  `AddNewColumnOperation._add_concat_column` uses
  `pl.concat_str(..., ignore_nulls=True)` and returns null only when every
  source is null. It raises `ValidationError` naming any missing or non-text
  source, so a reapplied step whose source changed type is skipped. The form
  lists only text columns and stores the separator through
  `prep_view._concat_separator`; `_is_add_column_incomplete` requires two
  columns and a non-empty **Specify** separator. The Stata prepare-data script
  joins the columns in a `foreach` loop that skips empty values
- **Prep to string** (#388): Transform Column has a `to string` operation
  (`PrepOperations.to_string`) for numeric, datetime, date and boolean
  columns. It casts in place with Polars' default string cast; floats drop a
  trailing `.0` and nulls stay null. Date and boolean columns get their own
  input path (`PrepDescriptions.CONVERSION_FUNCTIONS`,
  `_render_conversion_function_inputs`)
- **Prep to number** (#388): Transform Column has a `to number` operation
  (`PrepOperations.to_number`) for boolean columns. It casts in place to
  `Int64` (true → 1, false → 0, nulls stay null). Boolean columns get their own
  menu (`PrepDescriptions.BOOLEAN_FUNCTIONS`) with `to string` and `to number`.
  Imports keep boolean columns as booleans; this replaces the import-time cast
  proposed in #386. The Stata prepare-data script maps `"true"`/`"false"` text
  from the raw CSV to 1/0 and any other value to missing
- **Configuration bundle: check tables and missing codes** (#352, #354):
  `export_project_config` (`utils/project_config.py`) now exports each page's
  check tables (`CHECK_TABLE_PREFIXES`: duplicates, outliers, gps_columns,
  backchecks, descriptive_columns, bc_attribution) with a per-table dtype map
  (`PageConfig.check_table_schemas`), so list, decimal, date and datetime
  columns round-trip exactly; bundles without the map fall back to inferred
  types. Check tables are written right after a page's settings, so a page
  skipped on import writes none. The project's missing codes are exported
  and merged once per import, keyed by label with the bundle winning
- **Bundle version** (#354): Bundles carry `bundle_version`
  (`BUNDLE_VERSION = 2`). Importing a bundle without it shows
  `bundle_version_warning`: check tables and missing codes are not included
- **Export without record-level decisions** (#355): `export_project_config`
  takes `include_record_level` (default `True`). When `False`, the bundle
  omits corrections and the `RECORD_LEVEL_TABLE_PREFIXES` check tables
  (`bc_attribution`) and still imports cleanly. The project card's **Export
  configuration** entry opens `_export_config_dialog` (`views/start_view.py`)
  with an "Include record-level decisions" checkbox, so the bundle is built
  only when the dialog opens instead of for every card on every rerun
- **Check health changes over a comparison period** (#399, #365): Summary's
  check health rows gain a Change column and "+N since …" under Resolved. A
  collapsible **Comparison period** box above the rows offers Day (default,
  vs the end of yesterday), 7 days, Week (week to date, week start
  selectable, default Sunday), 30 days and Month (month to date)
  (`checks/health_period.py`: `ComparisonPeriod`, `period_start(period,
  today, week_start)`, `since_label`). The choice is one project-wide view
  setting in `settings/project_view_settings.json` (scope
  `health.PERIOD_SCOPE`), so project exports leave it out
  - `CheckEntry.delta` functions (`checks/health_deltas.py`) return a
    `CheckDelta` (outstanding change, resolved in the period, `DeltaKind`)
    for Progress, Missing Values, Duplicates, Outliers & Constraints,
    Enumerator Stats and Backchecks; `health_rows(..., deltas=, window=)`
    computes them and caches them under the period start (`DeltaWindow`,
    built by `health_deltas.comparison_window`; the week start is a
    `Weekday`). Progress, Missing Values and Enumerator Stats are recomputed
    on the submissions dated on or before the period start
    (`on_or_before`). Duplicates counts the unresolved duplicate IDs held by
    a submission dated in the period, including an ID already duplicated
    before the period that a new submission joins; Outliers counts current
    flags on submissions dated in the period. Resolved deltas count
    still-active entries made after the period start in `corr_log_{alias}`
    (`duplicates_delta`: an ID counts only when its latest removed record or
    changed or removed ID was logged in the period, not for an unrelated
    later entry; `ReviewContext.entries_after`) and `bc_attribution`
    (`backchecks_delta`); new `outliers_delta`. Every check counts an item
    only when it was unresolved at the period start: Outliers skips cells a
    check's flag was accepted or corrected on by then
    (`ReviewContext.resolved_by_period_start`), Backchecks compares the
    attributions then and now, and GPS dates a point by its first
    acceptance or correction (`GPSReviewLog.history`). The check-level delta
    functions take the `DeltaWindow`. Page config dicts move to
    `checks/check_configs.py`
  - A change that cannot be computed shows an error marker and the reason in
    the row's Change column (`HealthRow.delta_error`) instead of "—"; the
    row keeps its numbers and the delta is not cached
  - Rows use Summary's date column (its saved date, else the page survey
    date); Backchecks uses the backcheck date column. With no date column
    the box and Change column are hidden and a caption says "Set a date
    column in Summary settings to see changes over time." A caption shows
    the latest submission date
  - `CheckHeadline` gains `count` (Progress submissions, Enumerator Stats
    active enumerators); `enumerator_headline` takes `today`;
    `id_duplicates.resolved_ids` returns the resolved ID set
- **GPS check health row** (#399, #365): GPS Checks moves off "Status only".
  `gpschecks_headline` (`checks/gpschecks/report_ui.py`) detects outliers
  with the GPS configuration, detection method, clustering column and LOF
  sliders saved in the check's view, without rendering it or needing a Mapbox
  token. Outstanding is the check's **Outliers Detected**; resolved counts
  accepted points plus points with a `source="gps"` correction still in
  effect that are not outliers now. It returns None (blue **Ready**) with
  fewer than `LOF_MIN_POINTS` points or no clustering column, and raises
  `settings_no_longer_fit` when the GPS configuration no longer parses
  - `summarize_gps_outliers` (`checks/gpschecks/review.py`, pure) gives both
    the check's metric and Summary's row; `GPSOutlierSummary` exposes the
    marked outliers, `unreviewed()` rows (with every data column, including
    the survey date) and `resolutions` (KEY and latest log `date`) for a
    later delta. `gps_corrections` picks the in-effect GPS corrections,
    `GPSReviewLog` carries them with the active acceptances. Replaces
    `_mark_accepted_outliers`
  - The **Number of Neighbors** and **Expected Outlier Proportion** sliders
    are bound to the GPS view state (`outlier_n_neighbors`,
    `outlier_contamination`); `lof_neighbors` and `lof_contamination` apply
    the same defaults and fallback for a saved value out of range
  - `health_rows` takes `view_keys`, and `CheckEntry` gains `headline_view`
    (GPS: `gpschecks_headline_view`, the `HEADLINE_VIEW_KEYS` values), added
    to a row's cache key because the page fingerprint leaves view state out
  - Without a Mapbox token the GPS page still renders the outliers section
    (`_render_gps_outliers_checks(..., show_map=False)`): counts and table,
    no map
- **GPS check health change** (#399, #365): the GPS Checks row gets a
  Change and "+N since …": `gpschecks_delta` (`health_deltas.gps`)
  counts unaccepted outliers on submissions dated in the
  period (outliers are not detected again on the earlier submissions) and
  the resolved points whose first GPS acceptance or correction is in the
  period
- **Check health benchmark** (#399): `just bench-health [rows] [repeat]`
  (`scripts/benchmark_check_health.py`) times each check's headline and its
  delta for every comparison period, and Summary's rows without deltas and
  with each period's, on the demo data and a generated 50,000-row form. It
  flags any delta, and any period's end-to-end delta overhead, over the 1 s
  budget. None is over it: the slowest delta, Outliers, is about 0.3 s on the
  generated form in every period, and the deltas add 0.7 to 0.9 s to the
  rows end to end, so every delta is still computed on load
- **Demo project guidance** (#361 items 5-9, #365): demo guidance now covers
  the project-level features.
  - The Start page demo row (`start_view._render_demo_row`) has an **Export**
    button (key `demo_export`) next to Resume and Restart, shown once the demo
    exists. It opens the existing `_export_config_dialog` with
    `DEMO_PROJECT_NAME`, so the demo exports like any project; the bundle is
    built only when the dialog opens
  - `OnboardingSteps.OUTPUTS` asks for the sidebar **Reviewer name** before
    the first correction. `OnboardingSteps.CONFIGURE` edits only the survey
    target of the main page and removes a throwaway second page, so the
    walkthrough page survives; the page names and targets are named once in
    `DEMO_PAGE_NAME`, `DEMO_SURVEY_TARGET`, `DEMO_EDITED_TARGET` and
    `DEMO_THROWAWAY_PAGE`. `OnboardingSteps.REPLICATION` adds an **Exclude
    reviewer names** step and a project export from the demo row, and explains
    Update from configuration and Delete project without running them
  - New `ImportDemoInfo.SURVEYCTO_INFO` replaces the Import Data callout above
    Manage Credentials. It walks through the SurveyCTO credential and import
    forms without a server or credentials and says not to submit them
  - Tests: `TestProjectGuidance` checks that each label the new guidance names
    is in the guidance and in the source file that renders it, and that the
    loaded demo exports a bundle; `TestRenderDemoRow` covers the Export button
  - Files: `src/datasure/utils/onboarding_utils.py`,
    `src/datasure/views/start_view.py`, `src/datasure/views/import_view.py`
- **Demo guidance for check-page reviews** (#361, #365): `demo_callout`s walk
  through accepting a soft age violation and correcting a land outlier in
  the Outliers **Review** dialog (with **Show reviewed**), accepting a GPS
  outlier, attributing two backcheck mismatches (Enumerator without a note,
  Respondent with one) and reading the **Attribution log**, and checking the
  GPS columns under **Other Duplicates**. The values they name are new
  entries in `onboarding_utils.py` (`DEMO_AGE_BOUNDS`, `DEMO_OUTLIER_ACCEPT`,
  `DEMO_OUTLIER_CORRECTION`, `DEMO_GPS_ACCEPT`,
  `DEMO_BACKCHECK_ATTRIBUTIONS`, `DEMO_SHARED_LONGITUDE`), each tested
  against the real demo data in `TestReviewGuidanceValues`. The GPS
  outliers guidance moved into `_render_gps_outliers_checks`, so it also
  shows without a Mapbox token

### Changed

- **`render_health_rows` no longer draws the section header** (#399, #365):
  call `render_health_header()` first. It takes `since` (None hides the
  Change column)
- **Outliers and GPS deltas reuse the headline's flags** (#399, #365):
  `CheckHeadline` gains `basis` (not compared), what a headline computed its
  numbers from. `duplicates_headline`, `outliers_headline` and
  `gpschecks_headline` set it, and the deltas'
  `basis=` reuses it
  instead of computing the flags again (the Outliers delta computed them twice
  per load). `health_rows` keeps the latest basis per check outside the
  headline cache, matched to the headline's key. On a 50,000-row form the
  Outliers delta drops from about 0.9 s to 0.35 s and the GPS delta from about
  1.3 s to under 0.05 s. `_reviewed_flags` becomes `_outliers_basis`

- **Breaking: headline functions return `CheckHeadline`** (#399, #365):
  `progress_headline`, `missing_headline`, `duplicates_headline`,
  `outliers_headline`, `enumerator_headline` and `backchecks_headline` return
  a `CheckHeadline` (`checks/headline.py`: value, detail, outstanding,
  resolved, informational) instead of a sentence (`str`), and
  `CheckEntry.headline` is typed `Callable[[CheckContext], CheckHeadline |
  None]`. `duplicates_headline(data, setting_file, config)` becomes
  `duplicates_headline(project_id, data, setting_file, config, alias=None)`.
  `outliers_headline` and `backchecks_headline` raise `ValueError` (built by
  `settings_no_longer_fit`) when the saved settings no longer fit the data,
  instead of returning None
  - Migration: read `headline.value` and `headline.detail` where the
    sentence was used; pass `project_id` first and the survey alias to
    `duplicates_headline`; catch `ValueError` where a None was expected
    for stale settings (`overall_error_rate_percent` still returns None)
- **Check health rows** (#399, #365): Summary's check health card grid is
  replaced by one row per check, each in its own bordered box, grouped by
  navigation group under a shared
  Check · Status · Outstanding · Resolved header (`checks/health.py`:
  `health_rows` builds the `HealthRow`s, `render_health_rows` draws them,
  `group_rows` groups them once each in navigation order). Adding a
  catalogue entry adds a row with no layout change
  - The status pill (`st.badge`, `RowState.pill`: a `Pill` of colour, icon
    and label) has a `RowState` derived per row: grey **Not set up** and
    **Not applicable** and red **Error** from the config-only
    `CheckStatus`; a ready row is red when its headline raises, including
    when saved settings no longer fit the data (the other rows still
    render), amber **Flagged** when it has more than 0 outstanding and is
    not informational, blue **Ready** when it has no headline numbers (GPS
    Checks before outliers can be detected, or Backchecks with no values
    compared), so the pill claims
    nothing about uncounted issues, else green **No issues**. The row's action comes
    from its state (`RowState.action`)
  - A ready check with no headline numbers (Descriptive Stats)
    shows "Status only" (`STATUS_ONLY`) as its detail; Descriptive Stats
    stays green through the informational `status_only_headline`
  - `missing_headline` reports the % of columns all missing (was the mean %
    of values missing); `MissingSummaryStats` gains `all_missing_count` and
    `column_count`
  - `duplicates_headline` adds the resolved IDs (`_resolved_ids`, the
    check's survey "Resolved" count); without an alias the resolved count
    is None, shown as "—", since it cannot be computed
  - `outliers_headline` reports outliers plus violations as outstanding and,
    through `count_resolved_flags` (`checks/outliers/review.py`), accepted
    flags plus corrected cells no longer flagged as resolved; a corrected
    cell counts once for each check that flags it in the uncorrected data,
    which they rerun on only when some value was corrected
  - `backchecks_headline` reports mismatches with no error source as
    outstanding and attributed mismatches as resolved, over the categories
    of the total error rate (`TOTAL_CATEGORIES`, filtered by
    `in_total_categories` in `checks/backchecks/compute.py`); the detail is
    the total error rate. `_total_errors` is shared with
    `overall_error_rate_percent`
  - Progress and Enumerator Stats headlines are informational ("310 / 500",
    "4 / 12"), so their rows are never flagged; GPS Checks stays status only
- **Dependencies** (#393): `duckdb>=1.3.1,<3` (was `>=1.3.1`), lock moved from
  1.5.5 to 2.0.0; duckdb 3 is excluded until tested. `uv lock --upgrade` also
  moves plotly to 7.1.0, pyarrow to 26.0.0, starlette to 1.9.0 and
  jupyterlab to 4.6.4 (security fixes), folding in Dependabot #371.
  `astral-sh/setup-uv` 10.1.0 → 10.3.0 in `coverage.yml` and `release.yml`
  (#381); `uv_build>=0.7.19,<0.14.0` (#382)
- **Check table names in one place**: `CHECK_TABLE_PREFIXES`, one constant
  per prefix, `check_table_name()` and `missing_codes_table_name()` live in
  `utils/duckdb_utils.py`, and every check module and the export registry
  use them, so a renamed table can't silently drop out of exports
- **Enumerator consent and outcome flags** (#353):
  `add_consent_outcome_flags` (`checks/enumerator/compute.py`, cached with
  `st.cache_data` on the data and the settings) adds the flags from the
  page's saved consent and outcome settings each time the report runs. A
  flag is added only when its column and values are set; otherwise the
  "% consent" and "% completed survey" columns are hidden instead of showing
  100%. The consent and outcome column pickers no longer preselect a column
- **Bundle `missing_settings`** (#354): no longer exported, and applying a
  bundle no longer writes `page_<id>_missing_settings.json`. Bundles that
  contain the field still parse. `_decode_dtype` logs a warning before
  falling back to `String`

### Removed

- **Breaking: check health cards** (#399, #365): `health_cards`,
  `render_health_grid` and `HealthCard` are removed from `checks/health.py`
  - Migration: use `health_rows(ctx, items, headlines)` for the rows and
    `render_health_rows(rows, on_select)` to draw them; `HealthRow` replaces
    `HealthCard`, with `headline` a `CheckHeadline` and `state` a `RowState`
- **Apply Consent and Outcome Settings** (#353): The Enumerator settings
  button and the project-wide `enumerator_data_with_consent_outcome` table
  are removed; the flags are computed when the report runs

### Fixed

- **Stale demo guidance on check pages** (#361, #365): the Backchecks Summary
  callout said four metrics (five show, including Mismatches Attributed), the
  GPS outliers callout said the outliers could only be downloaded, and the
  Other Duplicates callout said to skip the section
- **Restart Demo did not reset the demo** (#357): After Restart, correction
  logs, page settings and per-check configs from the previous demo came back
  when the "Household HFCs" page was recreated, and Exit Demo left demo
  datasets in session state for the next project
  - Root cause: both Restart paths only called `load_demo_data`, which drops
    the raw/prep/corrected tables, prep logs and `check_config` but not
    `corr_log_*`, `page_*_settings.json` or the per-check tables in
    `logs.duckdb`. Exit Demo only cleared `st_project_id` and
    `onboarding_step`, and `import_view` keeps an existing
    `st_raw_dataset_list`
  - Solution: new `utils/demo_lifecycle.py`. `reset_demo_project()` clears
    the whole app's `st.cache_data` and the check headline cache, deletes
    `cache/demoproject/`, re-registers the project and reloads the demo
    data. The Start page Restart and Start Demo buttons
    (`start_view._launch_fresh_demo`) and the sidebar Restart Demo share it;
    the sidebar now confirms with `confirm_dialog` like the Start page, and
    both queue an error (`DEMO_RESET_FAILED_MESSAGE`) with `queue_notice` when
    the folder cannot be deleted, so the dialog's rerun no longer hides it.
    A failed reset removes the demo from `projects.json` and leaves it, so a
    partly deleted demo is not offered for Resume, and both Restart actions
    show the error on the Start page's demo row.
    `exit_demo()` and `reset_demo_project()` clear every session key except
    the app-wide page handles, the reviewer name, queued messages and other
    projects' navigation keys, then restore the defaults that `app.py` sets
    (now in `utils/session_defaults.py`), so no demo datasets, replication
    package or import log carry over. Demo keys are cleared even when a page
    name ends in 8 hex digits, like another project's ID. The Restart dialog
    (`RESTART_DEMO_MESSAGE`) lists what is deleted
  - Tests (#364): `tests/utils/test_demo_lifecycle.py` checks that Restart
    leaves only freshly loaded demo data and that a project opened after
    Exit Demo sees no demo state
  - Files: `src/datasure/utils/demo_lifecycle.py`,
    `src/datasure/utils/session_defaults.py`, `src/datasure/app.py`,
    `src/datasure/views/start_view.py`,
    `src/datasure/utils/navigations_utils.py`,
    `src/datasure/utils/onboarding_utils.py`
- **Demo ended three times** (#362, #365): The Backchecks comparison
  callout and the Correct Data guidance both said the demo was complete
  before the Replication step, and Replication said it again in a text-only
  callout; the completion message with Restart and Create Real Project was
  never shown
  - Root cause: each page added its own ending, and
    `show_demo_completion_message` was never called. Its Restart only set the
    onboarding step to 1, so it would not have reset the demo
  - Solution: `show_demo_completion_message` moved to
    `utils/navigations_utils.py` and is called once, from
    `views/replication_view.py` after the PII confirmation is ticked. Its
    balloons show once per demo run (session flag `DEMO_CELEBRATED_KEY`,
    cleared by Restart and Exit with the rest of the demo's session state),
    not on every rerun of the page. Its Restart opens the same confirm dialog as the sidebar Restart and runs
    `reset_demo_project()` (`_restart_demo`, shared by both); Create Real
    Project calls `exit_demo()` and opens the Start page. The other endings
    are removed, along with the unreachable "Congratulations" branch of
    `show_next_steps`
  - Tests (#364): `TestShowDemoCompletionMessage` and
    `test_completion_message_is_the_only_demo_complete_message` in
    `tests/utils/test_navigations_utils.py`; `TestDemoCompletion` in
    `tests/views/test_replication_view.py`
  - Files: `src/datasure/utils/navigations_utils.py`,
    `src/datasure/utils/onboarding_utils.py`,
    `src/datasure/views/replication_view.py`,
    `src/datasure/checks/backchecks/report_ui.py`
- **Demo data seeded and complete** (#360, #365): Every Start or Restart
  Demo drew new random dates, consent and completion values, so reports
  changed between runs; backchecks could predate their survey; and several
  checks the demo walks through showed nothing
  - Root cause: `DemoDataGenerator` (`utils/onboarding_utils.py`) used the
    global `random` module unseeded and dated backchecks independently of
    surveys, and the demo CSVs had no -88 values, almost no backcheck
    mismatches, an empty `land_acre` and the district "Anantapur" in `state`
  - Solution: `DemoDataGenerator(df, today=None, seed=DEMO_SEED)` draws from
    its own `random.Random(seed)`, so every load is identical apart from a
    whole-day offset that puts the latest survey submission on `today` (the
    current date by default; seeded data also has submissions yesterday, so
    Check health deltas show). `add_demo_fields("backcheck",
    survey_df=...)` dates each backcheck 1-5 days after the latest survey
    with its `hhid`, capped at `today` and always after the survey
    submission. `load_demo_data(today=None)` passes both through and no
    longer reads the backcheck CSV twice. The demo CSVs now have 13 -88
    values (`rooms`, `dist_sch`, `min_dist`, `pvt_sch`, `land_acre`),
    3-6 backcheck mismatches on each column the Backchecks guidance adds,
    `land_acre` filled for all but 8 of the 132 households (with some
    -99/-88 and three large outliers), and `state` "Andhra Pradesh" in place
    of "Anantapur". The data stays synthetic
  - Tests (#364): `TestRealDemoData` in `tests/utils/test_onboarding_utils.py`
    loads the real demo CSVs through `load_demo_data` and checks the seeding,
    backcheck dates, -88 values, `land_acre` outliers and backcheck
    mismatches
  - Files: `src/datasure/utils/onboarding_utils.py`,
    `src/datasure/assets/demo_survey.csv`,
    `src/datasure/assets/demo_backcheck.csv`,
    `scripts/benchmark_check_health.py`
- **Stale demo guidance** (#356, #365): Demo guidance named columns, widget
  labels and counts that no longer matched the demo data or the UI, showed
  two instruction sets on the Correct Data and Replication pages, and gave
  worked examples that produced little or nothing
  - Root cause: guidance text hard-coded column names and labels, so it
    drifted as the UI and the demo data changed
  - Solution: `DemoColumn` and `DemoBackcheckColumn` (`StrEnum`s in
    `utils/onboarding_utils.py`, collected in `DEMO_GUIDANCE_COLUMNS` by
    dataset alias) list every demo column guidance names, and the guidance
    f-strings use them, so adding a column to guidance means adding a member.
    The demo values guidance names (the duplicate `hhid`s, their KEYs and
    new IDs in `DEMO_DUPLICATES`, and the `land_acre` correction 75.5 to 5.5
    in `DEMO_LAND_CORRECTION`) are named once next to them, and the Prepare
    page's check for the `submissiondate` conversion reads the column from
    them too. Labels, section counts and metric names now match the Missing, Summary,
    Progress, Outliers, GPS, Enumerator, Backchecks, Prepare and Configure
    pages (for example `household_count` for `household_size`, no GPS
    accuracy or form version column, "Auto-Clustering (LOF)", "Total
    Columns"). Worked examples use the seeded data: a progress target of 3 a
    day against the demo's ~2.4, `household_count` and `land_acre` as
    outlier columns, and Modify ID / Drop on the Duplicates cards for all
    three duplicate `hhid`s (UP015-005, GJ013-025, and AN002-003, whose
    dropped record is a near-empty submission). The
    `summary_check_health` guidance describes the Check health columns,
    statuses and Comparison period. The Correct Data page keeps only the
    `OnboardingSteps.CORRECT` step guidance, now a `land_acre` correction;
    `ImportDemoInfo.ADD_CORRECTION_STEP_INFO` and its expander in
    `correction_view.render_page_header` are removed. The Replication page
    drops its copy of the `OnboardingSteps.REPLICATION` text
  - Tests (#364): `TestRealDemoData.test_every_column_named_in_guidance_exists`
    checks every `DEMO_GUIDANCE_COLUMNS` member against the real demo data;
    the `TestRealDemoData` duplicate and correction tests check that each
    duplicate pair and KEY exists, each new ID is unused, the dropped
    AN002-003 record is the emptier one, and 75.5 is an IQR outlier while
    5.5 is not
  - Files: `src/datasure/utils/onboarding_utils.py`,
    `src/datasure/checks/duplicates.py`,
    `src/datasure/checks/backchecks/report_ui.py`,
    `src/datasure/checks/enumerator/report_ui.py`,
    `src/datasure/checks/gpschecks/report_ui.py`,
    `src/datasure/checks/outliers/report_ui.py`,
    `src/datasure/views/correction_view.py`,
    `src/datasure/views/prep_view.py`, `src/datasure/views/replication_view.py`
- **DuckDB 2.0 compatibility** (#393): Fresh installs that resolved duckdb
  2.0 failed on the first table read or write, so data could not be imported
  - Root cause: duckdb 2.0 removed `.pl()` from `execute()` results and
    raises `ResourceInUseException` when a connection is reused while an
    `execute()` result is unfinished; the table-exists checks read it with
    `fetchone()`
  - Solution: `duckdb_get_table` reads Polars data through the relation API
    (`conn.sql(...).pl()`), and every table-exists check uses `fetchall()`.
    Both work on duckdb 1.x
  - Files: `src/datasure/utils/duckdb_utils.py`
- **Missing codes counted as values** (#379): The codes set on the Missing
  Values tab (for example `-99` for Don't know) entered the mean, the minimum
  and the outlier bounds in Outliers, Descriptive Statistics and Enumerator
  Statistics, so each code was reported as missing and as an outlier
  - Root cause: only `checks/missing.py` and the enumerator missing counts
    read the missing codes; every other numeric check used raw values
  - Solution: new `mask_missing_codes` (`checks/missing.py`) sets the numeric
    missing codes to null in the given numeric columns, skipping codes that
    are not numbers (such as `.d`). `compute_outlier_output`,
    `compute_constraint_violations`, `compute_summary_stats`,
    `compute_histogram_data`, `compute_enumerator_statistics` and
    `compute_enumerator_statistics_overtime` take an optional
    `missing_codes` DataFrame and mask the checked columns first. The codes
    are an argument, not loaded inside, so for the cached
    `compute_enumerator_statistics` they are part of the `st.cache_data`
    key. The report pages pass
    `load_missing_codes_from_db(project_id)`, as does the outlier column
    inspection's statistics and box plot. The inspection converts text
    columns to numbers before masking (new `_mask_inspection_column` in
    `checks/outliers/compute.py`) and shows a warning listing the excluded
    codes with their counts, for example `-99 (5), -77 (6)`. Missing Values
    keeps the raw codes.
    Back checks are unchanged: they have their own `no_differences_values`
    and `exclude_values` settings
  - Missing Values and the masked checks now parse codes with the same
    `_codes_as_dtype`. Before, Missing Values truncated decimal codes on
    integer columns, so a `.999` code flagged every real `0` as missing and
    `-99.9` flagged every `-99`. Decimal codes still match float columns, and
    `-999.0` still matches `-999` in an integer column
- **Enumerator summary dates** (#380): First and last submission and the
  today, this week and this month counts were wrong when the data spanned
  more than one month
  - Root cause: `compute_enumerator_summary` formatted the date column as
    `"%b %d, %Y"` text before taking `min`/`max` and comparing with `>=`
  - Solution: `compute_enumerator_summary` (`checks/enumerator/compute.py`)
    cuts the column to its local day (`dt.date()`) for every calculation and
    formats only the first and last submission columns for display, so the
    form-version check still groups per day. "Today" is still the system
    clock, now injectable through a new `today: date | None = None`
    parameter. `compute_enumerator_overview` takes the same `today`
    parameter and cuts dates to the local day the same way, so "active in the
    past 7 days" agrees with the summary. The summary table
    (`checks/enumerator/report_ui.py`) shows a "Data as of" note with the
    latest submission date from the new `compute_latest_submission_date`
- **Configuration export left out check settings** (#352): Applying an
  exported project setup lost missing codes, Descriptive Stats columns and
  the Duplicates, Outliers, GPS and Backchecks column rules
  - Root cause: these settings live in DuckDB tables, and the bundle only
    carried the settings JSON files
  - Solution: the check tables and missing codes are now in the bundle (see
    Added)
- **Descriptive Stats selection shared across pages** (#353): Choosing
  columns on one page changed them on every page
  - Root cause: the selection was saved once per project in
    `selected_columns_df`
  - Solution: each page saves its own `descriptive_columns_{page}` table in
    the logs database. A page with none is seeded once from the legacy table,
    keeping only its own columns; the legacy table is left in place. Export
    falls back to the legacy selection only when a page has no table, and
    import writes an empty table for a page bundled without one, so the
    legacy selection can't come back
- **Enumerator consent results out of date** (#353): The report read flags
  that only the Apply button built, so they were empty after an import and
  stale after a data refresh or a settings change on another page. They are
  now computed when the report runs (see Changed). Changing the consent or
  outcome column also saves its values, so old values are not read against
  the new column
- **Imported correction logs crashed Outliers & Constraints and GPS Checks**
  (#352): After applying a bundle whose corrections had no acceptances, these
  pages failed with `ComputeError: cannot compare string with numeric type
  (i32)`
  - Root cause: `_seed_correction_log` (`utils/project_config.py`) built the
    log with no schema, so the all-null `check_type` and `severity` columns
    had Polars' `Null` type, which DuckDB saves as `INTEGER`.
    `get_active_acceptances` then compared the Int32 `check_type` with a
    string
  - Solution: `ensure_log_columns` (`processing/correction_log.py`) casts any
    all-null column to its `CORRECTION_LOG_SCHEMA` type, which repairs logs
    already saved this way when they are read. `_seed_correction_log` runs
    the log through it before saving
- **Remove rows dropped rows with missing values** (#351): A "Remove rows"
  step with a condition also removed rows where the selected column was
  missing, and counted them as matches. With several columns selected, `>`,
  `>=`, `<`, `<=` and `between` removed a row only when all columns matched,
  while `equal to` and `like` removed it when any column matched
  - Root cause: `RemoveRowsOperation` (`processing/prep.py`) built the
    opposite of the condition and kept those rows (for example
    `filter(age <= 60)` for "greater than 60"). Comparing a null gives null,
    and `filter` drops null rows. The Stata replication script used the same
    `keep if` form, and Stata treats missing as larger than any number
  - Solution: each condition now builds a remove-mask that says what the UI
    says (`_equality_masks`, `_comparison_masks`, `_range_masks`,
    `_pattern_masks`). The column masks are combined with
    `pl.any_horizontal` and applied by one helper, `_drop_where`, which runs
    `filter(~mask.fill_null(False))`. A row is removed only when the
    condition is definitely true in at least one selected column, for every
    condition including `not equal to`, `not between`, `not like` and
    `not missing`. `_drop_where` counts the rows kept because of a missing
    value and puts the count in `additional_info`, for example
    `1 row kept because a value is missing in "age".`
    `PrepConfirmationMessages.remove_rows` adds it to the step description in
    the prep log
  - An empty string in a text column counts as missing, as `missing()` does
    in Stata, so DataSure and the exported do-file keep the same rows
  - Comparison and range bounds are converted to each column's type by
    `_bound`: numbers with `float()`, so bounds saved as strings work on
    numeric columns, and dates saved as text with `str.strptime`. Comparison
    steps on date columns had always failed with a `float()` error
  - Stata: `_stata_remove_rows` (`replication/prep_script_generator.py`)
    writes one `drop if` line per selected column with a missing-value
    guard, for example `drop if age > 60 & !missing(age)`. Before, it used
    only the first selected column. Several `equal to` values become
    `(code == 1 | code == 3)`
  - Row counts may change for saved steps: steps on columns with missing
    values keep more rows, and multi-column comparison, `between` and
    `not missing` steps may remove more rows

## [1.2.0a3] - 2026-10-21

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
  (`reset_filters_button`) that clears only its own view state, beside its
  settings section (`reset_filters_beside`), or beside its title on Missing
  Values and Descriptive Stats. `ViewState`
  takes any settings file, for reuse by Prepare Data and Corrections
- **Summary check health grid** (#376): After Progress, Summary shows a card
  for every other catalogue check with its group, status (text and icon) and
  either a headline or the reason it is not ready. "Open →" (ready or error)
  and "Set up →" (not set up) select the check through `select_nav_item`, so
  `?check=` follows (`checks/health.py`: `health_cards`,
  `render_health_grid`)
  - Six checks expose a headline function, registered as
    `CheckEntry.headline`: `progress_headline` (share of target, or
    submissions), `missing_headline` (mean % of values missing),
    `duplicates_headline` (unresolved duplicate IDs after Records to
    Include), `outliers_headline` (total outliers with the share of checked
    values flagged, and constraint violations, accepted flags left out),
    `enumerator_headline` (enumerators active in the past 7 days out of all)
    and `backchecks_headline` (total error rate).
    Descriptive Stats shows status only
  - Headlines run only for ready checks and are cached on the page's data,
    settings files, the logs and intermediate databases and the date; a
    headline that raises is shown on its card and not cached
  - `outliers_headline` computes the check's results without rendering it
    (`_reviewed_flags`); `database_path` (`utils/duckdb_utils.py`) returns a
    project database's file path; `CHECK_PARAM` and `check_nav_key` move to
    `checks/catalogue.py`

### Changed

- **Check page opens on the last viewed check** (#375): With no `?check=`
  URL parameter, a check page opens on the check last viewed on it, also in
  a new session. A valid URL parameter still wins
- **View state stays local** (#375): Project configuration exports leave out
  `view_state` (`without_view_state`), and the filters older versions saved
  with check settings even before the check is opened (`LEGACY_VIEW_KEYS`,
  `utils/view_state.py`). Applying a configuration keeps
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
  - Prepare Data's preview has a "Columns to show" filter, saved in
    `view_state` per dataset, with a Reset filters action beside the
    "Preview Prepared Data" header
  - Onboarding text and the user guide describe both pages' pills

### Removed

- **Summary's Data Quality section** (#378): Removed in favor of the check
  health grid, which now follows Progress. Its four donuts duplicated the
  Duplicates, Missing Values, Outliers & Constraints and Backchecks health
  cards but were computed differently (duplicates on Summary's own ID column
  and the raw data, missing values without missing codes), so Summary could
  show two different numbers for one check. The health cards use each
  check's own settings and corrections
  - Summary's Survey ID setting, which only fed the duplicates donut, is
    removed; `summary_settings` returns `(date, target)` and
    `SummarySettings` has no `survey_id`
  - Removed `summary_data_quality`, `calculate_data_quality_metrics`,
    `compute_summary_data_quality`, `DataQualityMetrics` and `CheckRates`
    (`checks/summary.py`), `summary_report(check_rates=...)` and
    `flagged_outlier_percent` (`checks/outliers/report_ui.py`)
  - The outlier rate and backcheck error rate stay on Summary, in the
    Outliers & Constraints and Backchecks card headlines
  - The demo guidance moves to the health grid (`summary_check_health` in
    `checks/catalogue.py`)

### Fixed

- **Summary, Progress and Missing Values filters are view state** (#373):
  Their filters, selections and time periods were saved with the check's
  settings, so they were exported, copied by templates and not cleared by
  Reset filters. They now bind to the check's `view_state` scope
  (`check_view` in `checks/summary.py`, `checks/progress.py`,
  `checks/missing.py`). An older settings file still loads: the values move
  from the check's settings into view state on first use
  (`ViewState.adopt_legacy`, `view_factory(..., legacy=...)`)
- **The other checks' view choices are view state too** (#375): The
  Descriptive Stats histogram and value counts choices, the enumerator
  periods, columns and statistics, the backcheck productivity period and
  staff statistics view, the outliers inspected column and the extra report
  columns of duplicates and outliers were still saved with the check's
  settings. They now bind to the check's `view_state` scope and move there
  from older settings files on first use. The enumerator productivity period
  is now restored (it was saved under a different key than it was read
  from), and the two enumerator week start pickers no longer overwrite each
  other
- **GPS detection choices are remembered** (#375): The GPS outlier
  detection method and clustering column and the comparison distance
  threshold reset whenever the user switched checks. They are now view state
- **A stale GPS configuration is not set up** (#374): GPS Checks counted as
  ready when its saved configuration's columns were missing from the data,
  as long as another column looked like GPS data. It is now not set up, with
  the reason (`gpschecks_status`)
- **Corrections empty state** (#377): A dimmed check page shows the shared
  not-set-up or error state (`nav_ui.render_empty_state`) instead of its own
  message
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
