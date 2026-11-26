# TECHNICAL CHANGELOG

All notable changes to DataSure will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **SurveyCTO data dictionary** (#398, `processing/form_dictionary.py`):
  `build_form_dictionary(project_id, alias, raw, missing_codes)` builds an alias's
  variable dictionary, rule-based PII flags (trusting publishable fields; no
  Presidio, so what the rules leave open is `may_contain_pii` / `unscanned`)
  and `stats_rows`, which count each column only over the rows where its
  question was asked and set the project's whole-number missing codes apart
  (`sentinels_from_missing_codes`; a code under two labels raises). `None`
  without a stored form definition. `form_table` raises when raw's columns
  and the stored schema differ, instead of dropping columns.
  `dictionary_xlsx` writes the workbook (Instructions, Variables, Choices,
  Summary stats) with `save_codebook`; flagged columns show counts, never
  values. Instructions describes each sheet and each Variables column
  (`VARIABLE_DESCRIPTIONS`). A calculate's label is blank and its formula is
  in the Variables `calculation` column.
  Choices lists each select's codes and labels once per list (`list_name`,
  `value`, `label`), and the Variables sheet's `choices` column names the
  list. The compiled XML does not keep XLSForm list names, so a list is
  named after its question; withheld `search()` lists are left out
- **Replication package** (#398): SurveyCTO aliases get
  `1_docs/2_codebooks/{survey}_dictionary.xlsx`, listed in the README
  (`generate_readme(include_form_dictionary=...)`), in place of
  `codebook.csv`: `replication.codebook.final_columns` adds each final-data
  column's `stata_name`, `final_missing_rate` and `final_unique` to the
  Variables sheet, by name (no sample values), and columns added in Prepare
  Data are appended. Other datasets keep `codebook.csv`. A SurveyCTO dataset
  (`form_id` set) without a stored form definition gets no workbook and an
  `on_warning` note (`NO_FORM_DICTIONARY`) saying to refresh the import. A
  form the dictionary cannot read (`ValueError`, `KeyError`,
  `pa.ArrowException` from `build_form_dictionary`) is logged and leaves the
  workbook out with a note (`NO_FORM_DICTIONARY_BUILD`) instead of stopping
  the build
- **Dictionary types for media SurveyCTO fills itself** (#398):
  `build_questions` typed a `binary` field with no body control (comments,
  text audit, audio audit) as an error, which stopped the replication
  package. It now uses `surveycto.xlsform.binary_type` (was `_binary_type`),
  which reads the bind's `class=`, for uploads and these fields alike
- **Typed SurveyCTO import** (#397): `SurveyCTOClient._import_regular_form`
  (`connectors/scto.py`) downloads the deployed form's compiled XML
  (`SurveyCTOAPIClient.download_form_xml`, `GET /forms/{id}/xml` with the same
  Basic auth as the data), parses it with `parse_contract` and casts the wide
  JSON with `cast_wide`. `typed_frame` converts the Arrow table to Polars,
  strips the UTC zone from timestamps (stored naive, as before) and keeps
  `formdef_version` as `Int64` for the enumerator check
- **Form definitions** (#397): `save_form_definition` / `load_form_definition`
  (`utils/duckdb_utils.py`) keep the XML in `form_definitions` in
  `logs.duckdb`, one row per alias and form version. Removing an import
  removes its rows
- **`datasure.surveycto`** (#397): the form contract (`xml_contract`,
  `xpath`) and the typed cast (`cast`), adapted from surveycto_python_dict at
  `d6f54f9` and maintained in DataSure from now on; `parse_contract` also
  reads XML bytes. Upstream's offline tests for them are in
  `tests/surveycto/`. Changes from upstream: a `search()` select's items are
  split into its literal choices (integer values, as in ODK Collect) and
  `Node.choice_columns`, the item naming its dataset's value and label
  columns, and `Node.choices_known` is False until its dataset's codes are
  read. A `search()` dataset named by a field whose calculate is not a
  literal (`concat(...)`, `if(...)`) is left unknown (`data_source["dataset"]`
  is `None`, `dataset_field` names the field) instead of failing the parse.
  XPath `round` takes a halfway value toward positive infinity
  (`round(2.5)` is 3), not to the even neighbour. A static choice filter
  using XPath the evaluator does not implement (`normalize-space(...)`) keeps
  every item and is marked `"unresolved"` in `Node.choice_filter`, with the
  list read per submission, instead of failing the import
- **`SurveyCTOAPIError.status_code`**: the HTTP status, or `None` when there
  was no response. Every HTTP error from `SurveyCTOAPIClient` also includes up
  to 500 characters of the response body, where SurveyCTO explains statuses
  such as its non-standard 430. A failed submission download keeps the
  status instead of becoming an "Unexpected error"
- **Form definitions keep the cast's Arrow schema** (#398):
  `save_form_definition` / `load_form_definition` also store the
  cast's serialized Arrow schema. `form_table` casts raw back to it,
  restoring the field metadata Polars drops. When raw holds earlier
  batches, `merged_schema` adds their columns, so a refresh with few or no
  new rows keeps them; earlier batches with no stored schema add raw's own
  columns, without form metadata. The schema is worked out before raw is
  saved, so a failure leaves raw unchanged. A `form_definitions` table from
  1.3.0a4 gains the `arrow_schema` column on first use; its rows load with
  no schema, and `build_form_dictionary` returns `None` for them until the
  form is imported again. Importing an alias as a server dataset deletes its
  definitions (`delete_form_definitions`)
- **`utils/missing_codes.py`** (#398): `codes_by_label` and
  `whole_number_code`, moved from `checks/missing.py` (were
  `_get_missing_code_pairs`, `_whole_number_code`) so non-UI code can parse
  missing codes without importing the Missing tab
- **`datasure.surveycto` dictionary modules** (#398): the dictionary
  (`questions`, `dictionary`, `survey`), skip-logic stats (`stats`),
  workbook writer (`codebook`) and PII rules (`pii`), adapted from
  surveycto_python_dict at `d6f54f9` and maintained in DataSure from now
  on. `stats_rows`, `save_codebook` and `classify(analyzer=None)` run from
  in-memory objects

- **Enumerator Report: Needs attention**: a list near the top of the report
  of the enumerators any check singles out, each with Flagged or Watch
  reasons
  - `checks/enumerator/attention.py` (Streamlit-free): `attention_rows`
    merges reasons from the report's own numbers (activity, interview
    length, missing answers, consent, completion, form version), Response
    Patterns' High and Moderate badges, and other checks' `IssueCounts`.
    Rules compare each enumerator with the rest of the team in view; rates
    need `MIN_SUBMISSIONS` (5). Thresholds are module constants
  - `checks/enumerator_flags.py`: one `by_enumerator` function per check
    (Duplicates, Outliers & Constraints, GPS Checks, Backchecks), named by
    the new `CheckEntry.by_enumerator` field. `catalogue.enumerator_other_checks`
    asks the ready checks, caches each on the page fingerprint and returns
    a failing check, or one whose status errors, as an `attention.LeftOut`
    the list shows
  - Each rule runs on its own: `attention_rows` returns an `AttentionList`
    whose `left_out` names a rule that raised (logged), and
    `report_ui._list_patterns` does the same for Response Patterns, so one
    failure names itself under the list and the other reasons still show
  - New per-check counters: `duplicates.duplicate_records_by_enumerator`,
    `outliers.report_ui.outliers_by_enumerator`,
    `GPSOutlierSummary.unreviewed_by`,
    `backchecks.report_ui.backcheck_mismatches_by_enumerator` (mismatches
    attributed to the backchecker or respondent left out). Each also counts
    the issues on records with no enumerator (`headline.ByEnumerator`,
    `EnumeratorMismatches.unattributed`), which `IssueCounts.unattributed`
    carries and `attention.unattributed_notes` names under the list, so
    each check's numbers add up to its own total. Duplicates counts records,
    so they add up to the tab's "Records involved", not its duplicate IDs
  - `health.cached_headline` returns a headline with its basis from Summary's
    cache; `health.cached_on_page` caches other page-level results with it
- **Enumerator Report: page controls**: one Period, Week starts on and Team
  control for every section (`report_ui._render_page_controls`). The Team
  filter narrows every section's data. The period and week start that
  Productivity and Statistics Over Time saved separately move to the page's
  `period` and `week_start` view state on first load
  (`_adopt_shared_controls`)
- **Response Patterns: Digit Preference** (#418, part of #158): a new
  section at the bottom of the Enumerator Report, in
  `checks/enumerator/response_patterns/` (`models.py`, `compute.py`,
  `settings_ui.py`, `report_ui.py`). `report_ui.enumerator_report` calls
  `render_response_patterns`, a fragment
  - `compute.compute_response_patterns(data, settings, enumerator_col,
    missing_codes)` (Streamlit-free) returns a `ResponsePatternResults`
    model; the UI only renders it. Missing codes are masked before types are
    inferred or answers scored
  - Digit Preference pools the terminal digit of the integer part
    (`floor(abs(x)) % 10`) across the selected integer and continuous
    variables, skipping those with a range under 10, no variation or no
    answers. A text column the user types as integer or continuous is
    converted to numbers, and answers that aren't numbers count as missing
  - Each enumerator's share of answers ending in 0 or 5 is divided by the
    rest of the team's (everyone but that enumerator), rounded to two
    decimals. `DIGIT_PREFERENCE_LEVELS` sets three sensitivity levels: High
    flags at 1.25× with at least 100 responses, Medium (default) at 1.5×,
    Low at 2×. Moderate means the next more sensitive level would flag the
    enumerator, its response minimum included. N/A means fewer responses
    than the minimum, or a team with no 0 or 5 endings
  - `ResponsePatternSettings` (selected variables, type overrides, minimum
    and warning sample sizes, and `digit_preference_sensitivity`,
    `range_compression_sensitivity` and `categorical_sensitivity`) is saved
    under `enumerators.response_patterns` in the page settings file;
    settings that no longer validate fall back to the defaults
  - `utils/column_references` lists the selected variables
    (`_NESTED_SURVEY_SETTING_KEYS`), so renaming one in Prep warns that the
    Enumerator stats settings use it
- **Response Patterns: Range Compression** (#419, part of #158): a second
  sub-tab, `compute._compute_range_compression`, on the same integer and
  continuous variables as Digit Preference (text columns typed as numeric
  are parsed the same way)
  - Per variable, `sd_ratio = enum_sd / team_sd` against the rest of the
    team, each side capped at its own 5th and 95th percentiles
    (`TRIM_QUANTILES`) first and the ratio rounded to two decimals. An
    enumerator's SD ratio is their lowest across variables
    (`RangeCompressionEnumerator.variables[0]`). Mean shift is not flagged;
    the 0–100 compression/shift score in #158 was dropped
  - `RANGE_COMPRESSION_LEVELS`: flagged at an SD ratio of 0.65 or less
    (High), 0.5 (Medium, default) or 0.35 (Low); `range_badge_band` gives
    Moderate when the next more sensitive level would flag
  - A variable is skipped for one enumerator below the minimum (or with
    fewer than 2 answers) or when the rest of the team has no spread
    (`SkipReason.TEAM_NO_VARIATION`)
  - The detail's histogram (`RangeVariable.bucket_edges`) shares buckets
    between the two series over the rest of the team's 1st to 99th
    percentile (`HISTOGRAM_QUANTILES`), with outlying values in the end
    buckets and whole-number edges when every answer is whole
- **Response Patterns: Categorical Response Patterns** (#420, part of
  #158): a third sub-tab, `compute._compute_categorical`, on categorical
  variables
  - Per question, each option's share for the enumerator and the rest of
    the team, over the union of options (an option one side never chose is
    0%). The gap is the difference in percentage points, rounded to one
    decimal; a question's result is its largest absolute gap and the
    enumerator's their largest across questions
  - `CATEGORICAL_LEVELS`: flagged at a gap of 15 pp (High), 25 (Medium,
    default) or 35 (Low); `categorical_badge_band` gives Moderate as the
    other checks do. Options are ordered numerically where they parse as
    numbers (`_option_counts`), so codes sort 1, 2, 10
  - `SkipReason.TEAM_NO_RESPONSES` marks a question only the enumerator
    answered
- **Progress tracking-file and master-list modes**: new pure module
  `checks/progress_tracking.py`. `TrackingSettings` (mixed into
  `ProgressSettings`) adds `tracking_target`, `tracking_unit`,
  `survey_unit`, `tracking_id`, `tracking_parents`, `strip_leading_zeros`
  and `tracking_display`. `detect_mode` works the mode out from the
  settings (never stored): no tracking dataset → `fixed`, a target column →
  `tracking file`, none → `master list`. `normalize_keys` casts IDs and
  units to text, trims spaces, treats blanks as missing, reads whole-number
  floats as integers and, with the toggle, strips leading zeros; no case
  folding. `read_tracking` returns a `TrackingReference` with
  `TrackingIssue`s: a repeated unit or ID, a setting not chosen or a column
  no longer there is a blocking error; a missing key drops the row with a
  warning and count; a missing, non-numeric or negative target counts as 0
  with a warning listing the units. `assign_units` takes units from the
  survey's unit column (tracking file) or through the ID (master list);
  `unit_levels` rolls parents up as sums and puts rows of units not in the
  dataset or with a target of 0, and unexpected IDs, in an `Untracked`
  group; `respondents` gives each master-list ID its status (Completed,
  Attempted not completed, Pending) and lists Unexpected IDs with their
  last submission date — #410
- **Progress result**: `compute_progress` uses its `tracking` argument.
  `ProgressResult` gains `issues`, `unit_levels`, `untracked_units` and
  `respondents`; `mode` and `sections` follow the mode (By unit with a
  tracking dataset, Respondents with a master list). In file modes the
  target is the dataset's total and the fixed target is kept but unused; a
  usable master list normalizes survey IDs the same way. New to-do cards:
  Unexpected IDs, Units below 50% of target and Untracked units.
  `compute_counts` and `progress_headline` take the tracking dataset, so
  Summary's Progress row and its delta agree with the page. With a
  tracking dataset's target, Completed, Remaining, % complete, the series
  and the pace count only rows in tracked units; other completed IDs go in
  the new `ProgressCounts.untracked_completed`, which the header names, so
  unexpected IDs and untracked units can't reach the target. Summary's
  headline cache key (`_page_fingerprint`) includes the tracking data. The
  page warns when a saved Target source column is no longer offered
  (`stale_tracking_columns`), and Prep's rename warning
  (`find_column_references`) covers a tracking dataset's Progress settings
  and `survey_unit` — #410
- **`resolve_progress(ctx)`**: returns a `ProgressResolution` (mode,
  target, achieved, basis "completed interviews" or "unique IDs", and the
  unit and parent `unit_levels`) for Project Overview (#431, #435) — #410
- **Progress UI**: `checks/progress_tracking_ui.py` draws By unit (level
  and filter as per-page view state, a table sorted lowest % complete first
  with a `ProgressColumn` bar, CSV export) and Respondents (status counts,
  one To visit table grouped by unit lowest progress first with each unit's
  % complete, Unexpected and Completed lists, extra master-list
  columns, CSV exports), and the tracking issues. The settings expander
  gains a Target source section; Total Expected Interviews is read-only in
  file modes. The header strip names the mode and dataset, and an
  attention pill links to the to-do cards. `progress_report` takes a
  `TrackingSource` (alias and rows) — #410
- **Tracking Dataset in the page config**: `render_tracking_dataset_selector`
  in the add and edit forms (excludes the survey and backcheck datasets).
  `CheckData` gains `tracking_data`, `tracking_state` and
  `tracking_data_with_rows`; `load_check_data` loads it with the corrected
  → prep → raw fallback — #410

- **Progress compute layer**: `compute_progress(data, settings, as_of,
  period="Day", tracking=None)` in `checks/progress.py` is the single, pure
  function the Progress page and headline draw from. It returns a Pydantic
  `ProgressResult` with `ProgressCounts` (Submissions, Unique, Completed,
  Remaining, percentage), the over-time `series` (`SeriesPoint`: each ID
  counted once, in the period of its first qualifying submission, with the
  current period marked `partial`), the cumulative `target_path`, the
  `CurrentPeriod` count against the per-period target, the `Pace`
  (projected finish, counting today as the first day, as the days left
  do, at the mean completions per day
  over the 7 days up to the last submission, hidden with fewer than 3 days
  of data or a zero pace; need-per-day
  to the field end date), the `ProgressStatus` the header's status box
  draws (on track, behind, no field end date, target reached, field end
  date passed, too little data or no recent completions), the mode, the
  visible tabs and the to-do items (none yet). `tracking` is unused until
  tracking-file and master-list modes land — #408
- **Progress settings**: `ProgressSettings` gains the completion condition
  (`consent`, `consent_vals`, `outcome`, `outcome_vals`, read through
  `condition()` and `has_condition`) and `field_end_date`. The consent and
  outcome pickers list only categorical columns, since a date value can't be
  saved as JSON and a failed save would leave the settings file truncated.
  When the column changes, the saved values the new column has are saved
  again, so `progress_headline` applies the same condition as the page.
  With the same column, saved values missing from refreshed data stay
  selected, so a refresh can't empty the condition. A selected null value
  matches null rows. When a prep step removes a saved consent or outcome
  column, the page warns that it counts without it
  (`stale_condition_columns`) — #408
- **Stata names in the replication package** (#449): every column name the
  package uses that Stata can't use gets a Stata name when the package is
  built
  - `processing/column_names.stata_name_map(names, edits)` (Streamlit-free)
    proposes the names: characters outside `[A-Za-z0-9_]` become `_`
    (accented letters are NFKD-folded to ASCII), a leading digit gets a `_`
    prefix, a reserved name gets a `_` suffix, names are cut to 32
    characters, and taken names get `_2`, `_3` … Valid names are never
    changed and are never taken by a proposal, nor are `reserved` names
    (`stata_names.PACKAGE_VARIABLES`, the variables the import scripts
    create). `edits` without an error from `stata_name_edit_errors` (rules,
    an unchanged or reserved name, or another edit) claim their names first
  - `replication/stata_names.py`: `package_column_names` lists the raw
    columns, then the names prep steps use and create
    (`prep_script_generator.prep_log_column_names`). Edits are stored per
    dataset in `stata_names_{alias}` in `logs.duckdb`
    (`load_stata_name_edits`, `save_stata_name_edits`).
    `updated_stata_name_edits` decides which table values count as edits:
    a value is an edit when it differs from the name the column gets without
    its own edit, so typing a proposal another edit took is reported as a
    clash
  - `build_replication_package(stata_name_edits=…)` builds the map and passes
    it to the generators. `generate_import_script` and
    `generate_scto_import_script` take `columns` and `name_map` and rename
    mapped columns right after import by CSV position (one group `rename`
    using `` `:word k of `ds_vars'' ``), labelling each with its DataSure
    name; the SurveyCTO script also uses the Stata names in its field lists
    and keeps the question text of a mapped field in its note only.
    `generate_prepare_data_script(name_map=…)` maps `source_columns` and
    `column_names` and labels columns created under a mapped name.
    `generate_corrections_script(name_map=…)` maps the corrected column and
    the key. The codebook lists Stata names. With nothing to map, the
    package is unchanged
  - The Replication page lists the mapped names in an editable table
    (`_render_stata_names`). It saves edits only when all of them can be
    used, otherwise shows the errors and disables the build; it warns when a
    saved edit no longer applies, and blocks the build when the column names
    can't be read. The names are read fresh on every render, as the build
    reads them (the raw columns through the new
    `duckdb_utils.duckdb_get_columns`, which reads no rows). Edits aren't part of the exported project configuration
- **Rename columns** (#446): new Prep action **rename column(s)**
  (`PrepActions.rename_column`), with methods **by name** and **by pattern**
  (`PrepMethods.by_name`, `PrepMethods.by_pattern`)
  - `processing/rename_plan.py` (Streamlit-free) holds the rename plan:
    `plan_rename(columns, spec)` resolves a `ByName`, `Wildcard`,
    `ChangeCase` or `RegexRename` spec into a `RenamePlan`. The plan has the
    pairs in column order, the collisions, invalid (empty) names, missing by-name
    columns, the matched columns, per-row `problems`, and a spec-level
    `error`. Renames apply all at once, so swaps and chains are allowed. Names
    are compared ignoring case, as DuckDB does. Wildcards are Stata's `*` and
    `?`, matched against the whole name, with earlier `*`s matching greedily;
    `#` and `=` are rejected. Regex uses `re.fullmatch` and `Match.expand`.
    `spec_to_args`/`spec_from_args` are the logged form, and
    `describe_pattern` is the readable form
  - `processing/prep.RenameColumnsOperation` applies the plan with
    `DataFrame.rename`, which keeps column positions. By name skips old
    columns that are gone (`failed_count`, `additional_info`) and fails when
    none are left. A pattern that matches nothing fails. Collisions and empty
    names fail the step, so replay never overwrites a column. The request is
    logged in `value` (`[[old, new], …]` by name, `[mode, a, b]` by pattern).
    Each run's resolved pairs go in `source_columns` → `column_names`, and
    `_build_log_from_outcomes` keeps a successful rename's args from that
    run, so pattern steps record what they matched on the latest re-import.
    `PrepConfirmationMessages.rename_columns` describes the step
  - `prep_script_generator._stata_rename_columns` writes one
    `rename (old …) (new …)` from the recorded pairs, with a `* Pattern:`
    comment for pattern steps. With no recorded pairs, or a new name Stata
    can't use, the step is a NOTE with a warning. A step of any kind whose
    log status is `Failed` is written as a skipped-step comment, since it
    changed nothing (#449: a failed copy-of-column step used to be written
    as a live `clonevar` and stopped the do-file with r(110))
  - `utils/column_references.py` (Streamlit-free, read-only):
    `find_column_references(project_id, alias, columns)` reports where a
    dataset's check pages use the columns, as survey or backcheck data. It
    reads the `check_config` fields, the duplicates, outliers, backchecks, GPS
    and descriptive check tables, and the check settings files without view
    state. It also counts `corr_log_{alias}` entries per column, including GPS
    acceptances' coordinate columns
  - The Prep form (`PrepStepHandler.rename_column_handler`) has a by-name
    `st.data_editor` table and wildcard, change-case and regex inputs. It
    shows a live old → new preview (`_rename_preview`) with problems on their
    rows, and `_is_rename_incomplete` disables **Add** unless
    `RenamePlan.can_apply`. Before adding, `_add_rename_step` opens
    `confirm_dialog` listing any references; nothing is rewritten
- **Duplicate a column** (#445): Add new column has a new **copy of column**
  method (`PrepFunctions.copy`). `AddNewColumnOperation._add_copy_column`
  inserts a copy of one source column right after it, keeping its dtype and
  nulls. It raises `ValidationError` when the source is missing or the new
  name already exists, including on replay. The step is
  logged with the new name in `column_names` and the source in
  `source_columns`. `prep_script_generator._stata_add_column` translates it
  to `clonevar <new> = <old>` plus `order <new>, after(<old>)`. The Prep form
  picks the source first and prefills the name as `<source>_copy`
- **Stata name rules for the replication package** (#445): new
  `processing/column_names.stata_name_error` (Streamlit-free) reports names
  Stata can't use: over 32 characters, not starting with a letter or `_`,
  characters outside `[A-Za-z0-9_]`, or a reserved name
  (`STATA_RESERVED_NAMES`, from [U] 11.3, plus `str#` types; matched
  case-sensitively). Prep doesn't apply these rules, since not every user
  exports to Stata. `prep_script_generator._stata_add_column` uses them to
  write an add-column step whose new name Stata can't use as a NOTE with a
  Replication page warning, instead of a line that fails in Stata. Mapping
  names to Stata-safe ones when the package is built is tracked in #449

- **Headless keyring guidance**: `secure_credentials.keyring_backend_problem`
  detects a keyring backend that can't hold credentials safely: keyring's
  "fail" backend (headless Linux with no Secret Service) and plaintext file
  backends. Keyring errors from `store_scto_credentials` and
  `test_keyring_availability` now append an explanation that points to the
  README's new "Running on a server" section. A working plaintext backend
  still reports success but carries a `warning` that **Keyring Diagnostics**
  displays, and the diagnostics list a headless-server tip
- **Read-only notice**: when a project's settings folder contains a
  `.readonly` marker (`cache_utils.READ_ONLY_MARKER`), `app.py` shows its
  text as a warning above every page (`cache_utils.read_only_reason`; an
  empty marker gives a generic message, long text is cut to 300
  characters, an unreadable marker is ignored). DataSure never writes the
  marker: a host that opens a project read-only, such as a multi-user
  deployment where another user holds the project's write lock, drops it
  so users see why edits won't be saved before they hit a write error
- **Record project activation**: opening a project from the home page
  (`start_view._activate_project`) now stamps `last_used` in
  `cache/projects.json` via `_record_last_used`. The "Last used" caption
  and sort reflect when a project was last opened, not only when it was
  created, and tools that manage the cache (such as a hosted deployment's
  per-project write lock) can tell which project a user opened most
  recently. `last_used` changes when a project is opened, not while it is
  in use, so its age doesn't show whether a project is still open. A
  registry that can't be written is logged and doesn't block opening the
  project

- **Progress Follow-up section**: `compute_progress` now returns the
  Follow-up section's numbers in `ProgressResult`: `follow_up` (`FollowUpMetrics`: need
  follow-up, first-try rate, average attempts per completion and open after
  3+ attempts, plus the repeat-ID metrics that hold without a completion
  condition), `attempts_to_outcome` (`AttemptBucket` for attempts 1, 2, 3 and
  4+: completed at, open with exactly that many attempts, and submitted
  that many times; the average counts attempts up to the first completion) and
  `follow_up_queue` (`QueueRow` per open ID, sorted by attempts then days
  since the last attempt, each with its `Attempt` history; empty without a
  completion condition). The last outcome comes from the condition's outcome
  column, or reads "not complete" without one; the enumerator comes from the
  page config's enumerator column, now in `progress_config`. The new
  `display_follow_up` draws the metrics, a grouped attempts-to-outcome chart
  (`attempts_figure`) and the queue with last-outcome and minimum-attempts
  filters (saved view state), a CSV download (`filter_queue`, `queue_frame`)
  and the selected row's attempt history. The Follow-up section title
  carries a count badge when the queue has rows (`follow_up_title`), and
  Overview shows a "Respondents open after 3+ attempts" to-do card, only
  above zero, that links down to the section. `section_header` gains an
  `anchor` argument so the link survives the badge changing the title.
  Without a survey ID column the follow-up fields stay empty, because each
  row would count as its own ID — #409

### Changed

- **Breaking, SurveyCTO column types** (#397): columns take the form's types
  instead of `DataProcessor`'s. Integers are `Int64` (were `Float64`), dates
  `Date` (were `Datetime`), numeric select_one codes `Int64` (on a `select1`
  or a `string` bind) and select_multiple binaries `Int8` with 0 for unchosen
  options of an answered question (both were `String`), `duration` `Int64`
  (was `Float64`). A field the cast cannot parse in every row stays `String`.
  A `search()` select takes its codes from a dataset, so its select_one stays
  `String` and its select_multiple gets binaries only for the codes someone
  picked. A choice binary whose choice cannot be recovered
  (`ambiguous_choice`) stays `String` under its own name. A select_multiple
  exported raw and blank in every row keeps its binaries, all missing; one
  whose choices are only known when picked keeps its raw column, all
  missing, so an unanswered question stays visible. Prep or correction
  steps that relied on the old types report `Failed` on the next replay
- **Form or dataset routing** (#397): `import_data` imports an ID as a server
  dataset only when its form XML cannot be downloaded or parsed and the ID is
  on `list_datasets()`. The status SurveyCTO answers for a dataset ID's form
  XML is undocumented, so any XML failure checks the list, not only a 404.
  Submission, decryption and save errors raise instead of being retried as a
  dataset, which had turned them into a silent untyped CSV import or a
  misleading 403 from the dataset endpoint. When the dataset list itself
  fails (an account without dataset access), the form's own XML error is
  raised, not the listing's. A form import makes no dataset call, so accounts
  without dataset access import forms as before
- **Connection errors are classified by HTTP status**:
  `SurveyCTOClient._handle_api_error` maps 401, 403 and 404 from
  `status_code`, and matches keywords only for errors with no status. The
  message now carries SurveyCTO's response body, whose words could match an
  unrelated keyword
- **`SurveyCTOAPIClient.list_datasets`** (#397) follows `nextCursor` and
  returns the `data` entries (it returned the first raw page)

- **Needs attention layout** (`checks/enumerator/report_ui.py`): metrics for
  Flagged and Watch enumerators (an enumerator with both counts under both,
  `attention.attention_totals`) and enumerators listed replace the "N flagged
  and N to watch" caption. "Show Flagged" and "Show Watch" toggles, saved as
  view state, filter the list (`attention.shown_rows`); rows are labelled
  "2 flagged · 1 watch" (`attention.row_label`, replacing `flag_counts`), and
  reasons within a row sort Flagged first, then by check
- **Needs attention rules** (`checks/enumerator/attention.py`):
  - Interview length and missing answers count only consented and completed
    interviews when consent or outcome is set up (`counted_interviews`,
    `ColumnRoles.consent`/`completed`); missing answers then read
    `compute.compute_attention_summary` over those interviews,
    passed to `attention_rows` as `missing`
  - Form version: older-version submissions all within `FORM_VERSION_GRACE`
    (1 day) of the newest version's release are Watch, not Flagged
  - Response Patterns: a High badge on a low-sample result is Watch
  - GPS: fewer than `GPS_FLAG_POINTS` (3) unreviewed points are Watch, via
    the new `IssueCounts.flag_from`
  - Missing answers read "% Null values" when the project has no missing
    codes (`missing_column`); before, the rule needed "% Total Missing" and
    never ran without codes
- **Enumerator Report overview**: four figures with comparisons
  (`compute.compute_overview_figures`, `models.OverviewFigures`) replace
  the eight metrics. The old Fewest/Highest/Average "enumerator submissions"
  were per enumerator per day; the new figure uses each enumerator's total
- **Enumerator Report layout**: a caption names the columns in use; one
  message replaces the five "requires a date and enumerator" boxes;
  sections use `section_header` and `st.divider()`; selector labels lose
  "Select ..:"; `response_patterns.report_ui.cached_response_patterns` is
  public so the list reuses the section's cache
- **Progress page**: Rebuilt as the settings expander
  (`progress_report_settings`, with "Reset filters" beside it, as on
  Summary), then a header shown on every tab (`display_progress_header`:
  the percentage and completed count above an `st.progress` bar, capped at
  full by `progress_fraction` when completions pass the target, a status box
  saying whether fieldwork will finish on time, and a `metric_row` of
  Submissions, Unique, the current period, Pace and Days left, replacing the
  six-column row that cut off the projected finish date; the "Need N/day"
  line under the chart moves into the status box) above Overview (`display_overview`, with the Cumulative / Per period chart
  from `progress_figure`) and Follow-up (the unchanged attempted
  interviews). The chart's series ends at the period of the last
  submission, not today's. Submissions dated after today are left out of
  the series, the current period and the pace (they still count as
  Completed), so a wrong device clock can't stretch the chart past today.
  `progress_headline` uses the new `compute_counts`, which skips the series
  and pace, so a mis-keyed date can't slow Summary. The open tab (`progress_tab`) and chart view
  (`progress_chart_view`) are saved view state with the time period — #408
- **Progress headline and delta**: `progress_headline` now reports
  Completed out of the target. The delta re-runs it on the rows dated on or
  before the period start, so it counts IDs first completed in the period;
  `DeltaKind.SUBMISSIONS` is renamed `DeltaKind.COMPLETIONS` ("▲ 3 new
  completions since …") — #408

- **Progress page layout**: Overview and Follow-up are now sections one
  after the other on the page instead of tabs. `ProgressResult.tabs` is
  renamed `sections` (`SECTIONS_BY_MODE`) and `TodoItem.tab` is renamed
  `section`; the open tab (`progress_tab`) is no longer saved view state —
  #409

- **No more NOTE for names Stata can't use** (#449): `_stata_add_column` and
  `_stata_rename_columns` no longer write a step whose new name Stata can't
  use as a NOTE with a warning (the #445 stopgap); the step is written with
  the mapped Stata name
- **Add new column never overwrites a column** (#445): every Add new column
  method now refuses a new step whose name already exists, ignoring case
  (DuckDB would otherwise store `Age` beside `age` as `Age_1`). The form and
  `_apply_single_action` share `column_names.existing_name_error`. Before, a
  constant, calculated, concat, index, uuid or random column with an existing
  name replaced that column. Replays don't run the check, so steps saved
  before this change still replay as they did; a copy step whose name is
  taken on replay fails instead
- **Add new column form order** (#445): `PrepStepHandler.add_column_handler`
  now asks for the method before the column name, so **copy of column** can
  prefill the name from the chosen source

### Removed

- **`DataProcessor`** and `SurveyCTOConfig.date_format`
  (`connectors/scto.py`): replaced by `surveycto.cast`, which also replaces
  the 1.2.1 date parsing fix (#395)
- **`get_repeat_columns`**: replaced by `media_columns(contract, columns)`,
  which picks a media field's columns through `FormContract.map_column`, so
  a sibling field sharing the prefix (`photo_1` beside `photo`) is never read
  as media. Typed siblings crashed the import. `MediaDownloader` now takes
  column names and skips a column that is missing (no submissions, an empty
  repeat) or not a string
- **`SurveyCTOClient.get_form_definition`**: the import no longer reads the
  design endpoint. `SurveyCTOAPIClient.download_form_definition` stays for
  the Replication page's XLSForm

- **Progress**: The Enumerator setting (dropped from `ProgressSettings` and
  `progress_config`; saved values are ignored, so existing projects need no
  migration), the never-shown consent and completion donut code
  (`compute_progress_chart`, `display_progress_chart`, `ProgressChartMetrics`
  and `utils/chart_utils.py`), and the code replaced by `compute_progress`
  (`compute_progress_summary`, `display_progress_summary`,
  `compute_progress_overtime`, `compute_average_interviews`,
  `display_progress_overtime`, `ProgressSummary`,
  `AttemptedInterviewsMetrics`) — #408
- **Progress**: The per-ID attempted interviews table with its "Attempt
  Date N" columns and its model and helpers (`AttemptedInterviewsResult`,
  `compute_attempted_interviews`, `display_attempted_interviews` and their
  private helpers), replaced by the Follow-up section — #409

### Fixed

- **Replication package replaying corrections DataSure skipped** (#480):
  `generate_corrections_script` (`replication/script_generators.py`)
  dropped only "accept" rows, so a correction whose log `status` is
  `Failed` (say, a "modify value" on a column a prep step now drops) was
  written as a `replace` and stopped `4_corrections.do` with `variable ...
  not found`. Such a row now gets its comment and a "Skipped" note, as
  `prepare_data.do` already did for failed prep steps.
  `package_builder._applied_corrections` leaves failed rows out too, so the
  README's correction count and per-action summary match the do-file
- **Progress consent and outcome settings not restored** (#450): the old
  pickers saved both columns under one `chart` key and never preselected
  the saved values, so both were empty when the check reopened. The #408
  completion condition (`checks/progress.py`, `_render_condition_part`) saves them under
  `consent` / `consent_vals` and `outcome` / `outcome_vals` and restores
  both; a regression test covers the round trip. A project saved before
  this has only `chart`, which is ignored, so its consent and outcome
  columns must be chosen once more
- **Stata name mapping edge cases** (#463)
  - A valid column could keep Stata's `v#` name after import: Stata imports
    `visit date` as `visitdate`, so a later real `visitdate` column became
    `v3`. `script_generators._rename_imported_columns` now writes every
    column's package name in order (`local ds_names`), and the do-file
    renames each CSV position whose imported name differs, valid names
    included, in one group `rename`. It stops with an error (`exit 459`)
    when Stata imported a different number of columns than the CSV has
  - Variables rebuilt with `gen` + `drop` + `rename` lost their label, so a
    mapped SurveyCTO date or datetime field, or a mapped column after a
    Prep "to string" / "to number" step, had none.
    `scto_import_generator._emit_format_date_fields`,
    `prep_script_generator._stata_to_string` and `_stata_to_number` now save
    the label in `ds_label` and restore it with `macval`
- **Aliases and check page names sharing storage or breaking file names**
  (#350): `baseline-1`, `baseline_1` and `Baseline 1` were all accepted but
  mapped to one DuckDB table, so importing one replaced the other; page
  names such as `HH HFC` and `hh-hfc` shared a settings file and check
  tables; `HH/HFC`, `HH?` and `Round 1: HH` crashed the check page or wrote
  settings to an NTFS alternate data stream; and aliases with `-`, `.`, a
  leading digit or a SQL keyword were missing from the Import preview list
  - Root cause: duplicates were checked on raw names while storage used the
    cleaned ID, and callers built IDs in different ways
  - Solution: new `utils/names.py` holds the one name rule. `name_problem`
    allows a leading letter then letters, digits, spaces, `_` and `-`, up to
    `NAME_MAX_LENGTH` (20, now shared by local and SurveyCTO aliases).
    `name_id` (moved from `duckdb_utils`, unchanged formula, so no
    migration) gives the storage ID, and `name_clash` compares IDs and names
    the clashing entry. `FileConfig`, `FormConfig` and `CheckConfiguration`
    enforce the rule through `validate_name`; validating with the
    `STORED_NAME` context skips it and returns the name exactly as saved, so
    names saved before the rule still load and refresh into their own table,
    and unchanged names can still be edited. Aliases are compared with
    `duckdb_utils.alias_clash`, which uses the final DuckDB table name
    (`alias_table`), so `select` and `select_table`, or a saved `baseline.1`
    and a new `baseline_1`, are caught; bundle import compares the trimmed
    alias the importer saves. `ConfigurationService`
    (`page_name_exists`, new `page_name_problem`, add and edit validation),
    the local import form and `SurveyCTOUI._add_form_to_project` reject
    clashes by ID; a case-only rename of a page's own name is allowed.
    `apply_project_config` skips a bundled dataset or page that clashes by
    ID with an existing one, naming it, keeps bundled SurveyCTO aliases over
    20 characters, and writes page settings and check tables under the
    trimmed page name. `ConfigurationService.page_name_exists` is replaced
    by `page_name_clash`, which returns the message. `validation_message`
    turns a model's validation errors into plain text.
    `duckdb_get_imported_datasets` matches aliases with the same
    `_validate_table_name(name_id(...))` used to create tables. The
    SurveyCTO alias suggested from the form title uses `suggest_name`, empty
    when no valid name results. Replication package file names use `name_id`
    for the page part
- **SurveyCTO imports and replication questionnaires failing with HTTP
  430** (#469): SurveyCTO refuses the form design endpoint with 430, "your
  Excel form cannot be loaded until it is optimized", for some forms, and
  the console offers no way to optimize them
  - Root cause: the import read column types and attachment media fields
    from the design endpoint (`get_form_definition`), and the Replication
    page built the questionnaire XLSX and `import_data.do` from it
    (`SurveyCTOAPIClient.download_form_xlsx`)
  - Solution: types come from the compiled XML (#397), and the media fields
    from it too: `media_field_names(contract)` lists every `binary` bind,
    uploads as well as comments, text and audio audits and sensor streams.
    On a 430, `download_form_xlsx` rebuilds the design-shaped definition from
    the XML with the new `surveycto.xlsform.design_from_xml` (XLSForm types,
    begin/end group and repeat rows, `${field}` references outside quoted
    string literals, one choice list per select named after it, default
    language only; a `search()` select's list keeps the row naming its
    dataset columns and a `pulldata()` select its choices; a filtered list
    keeps its `choice_filter`, and the choices sheet the item columns the
    filter reads) and marks it
    `rebuilt_from_xml`; the Replication page says the questionnaire was
    rebuilt. `Node.bind_appearance` keeps the bind's appearance, which names
    comments and audit fields. A 430 from `download_form_definition` itself
    says the form must be optimized and to contact SurveyCTO support

- **Enumerator Summary**: % Consent and % Completed showed the 0 to 1 rate
  with a % sign (0.94%); they now use the `percent` format (94%)
- **Summary's Enumerator Stats row**: it could disagree with the Enumerator
  Report's "Active in the past 7 days". Root cause: the row used
  `compute.compute_enumerator_overview`, which counted any submission after
  the cut-off as active (including dates after today) and counted rows with
  no enumerator as an enumerator, while the overview used its own rule.
  Both now call `compute.count_active_enumerators` (in
  `checks/enumerator/compute.py`): the 7 days up to and including today,
  rows with no enumerator left out. `compute_enumerator_overview` and
  `models.EnumeratorOverviewMetrics` are removed; `report_ui.enumerator_headline`
  uses the new function, and the overview's help says when a chosen team
  makes it differ from Summary
- **Needs attention: Form version**: `attention.form_version_reasons` took
  the newest version as the text maximum, so with versions stored as text
  "9" beat "10" and the enumerators on the real newest version were
  flagged. It also compared by day, so older-version submissions made
  earlier on the update day counted as outdated. Versions now compare as
  numbers when they all are (as text otherwise); with a datetime date
  column only submissions after the newest version's first one count, and
  with a date-only column only those from the next day
- **Needs attention: Interview length**: `attention.duration_reasons`
  compared each enumerator with the median over every submission,
  including their own, so an enumerator who did most of the interviews set
  their own benchmark and was never flagged. Each is now compared with the
  median of the rest of the team's submissions, and the finding says "for
  the rest of the team"
- **Needs attention: Missing answers, Consent, Completion**:
  `attention.missing_reasons` and `rate_reasons` took the team median over
  every enumerator, including the one being judged, so in a small team an
  enumerator's own share pulled the benchmark towards them (two
  enumerators at 2% and 30% missing gave a 16% median, and 30% was not
  flagged). Each is now compared with the median of the other enumerators
  (`_rest_of_team_median`), and the finding says "for the rest of the
  team". The rate gap is rounded, so a 15-point gap is not read as 14.99
- **Needs attention: Team filter**: with a team chosen, other checks still
  counted each enumerator's issues across every team, against that team's
  submissions only, so an enumerator who worked in two teams brought the
  other team's issues along. The per-enumerator counters
  (`duplicate_records_by_enumerator`, `outliers_by_enumerator`,
  `GPSOutlierSummary.unreviewed_by`, `backcheck_mismatches_by_enumerator`)
  now take a `headline.EnumeratorScope` (enumerator column, team column,
  chosen team) in place of the enumerator column, and count only the
  chosen team's records; checks still find their issues on all records.
  `catalogue.enumerator_other_checks` caches on the scope, and the
  catalogue's `ByEnumerator` callable alias is renamed `CountIssues` so it
  no longer shares a name with `headline.ByEnumerator`
- **Progress targets**: Targets entered on the Progress page did not load
  back, so the page config's survey target always won on reload
  - Root cause: `progress_report_settings` saved the targets under `target`
    and `target_per_period`, but `ProgressSettings` reads `survey_target`
    and `target_submissions_per_period`, so `load_default_settings` ignored
    them
  - Solution: the targets are now saved under the `ProgressSettings` field
    names, and `load_default_settings` maps the old keys
    (`LEGACY_TARGET_KEYS`) so targets already saved still load. An old
    target loads only when the page config has no value for that field,
    because the config may have been set after it — #407
- **A failed write could empty the project registry, and sessions sharing
  a cache could undo each other's changes**: every read and write of
  `cache/projects.json` now goes through `utils/project_registry.py`, which
  writes to a temp file and swaps it in with `os.replace`, and holds an OS
  file lock across each read-modify-write. A corrupt registry no longer
  crashes the home page; it reads as empty and is kept as
  `projects.json.corrupt` on the next write
- **Replication package crashed on row-index ranges, and Stata dropped the
  wrong rows** (#442): building the package raised
  `ValueError: invalid literal for int() with base 10: '0:30'` when a
  **remove row(s) → by row index** step used a range. Even without a range,
  `prepare_data.do` dropped the wrong rows, and negative indices removed
  nothing or the wrong range in DataSure itself
  - Root cause: `_drop_by_index` in
    `src/datasure/replication/prep_script_generator.py` called `int()` on
    every value and copied DataSure's 0-based positions into Stata's 1-based
    `in` and `_n` unchanged. `RemoveRowsOperation._remove_by_index` matched
    raw values against non-negative row numbers, so `-5` and `5:-2` did not
    count from the end
  - Solution: new Streamlit-free `src/datasure/processing/row_index.py`
    (`parse_row_indices` → `RowSpan`, `resolve_row_positions`) is shared by the
    prep engine and the generator. Values are a position, a negative position
    counting from the end, or an inclusive `a:b` range. Earlier prep logs'
    string values, `","` and `None` entries still parse; anything else raises
    `ValueError`, which the engine reports as `ValidationError`. The generator
    emits one `drop if` over `_n` (`_n == i+1`, `inrange(_n, a+1, b+1)`,
    negative ends as `_N - k`), so all values refer to positions before the
    step. It never emits `drop in`, which stops with r(198) on positions
    outside 1.._N or reversed spans, where `resolve_row_positions` ignores them
  - The SurveyCTO `2_import_data.do` (`scto_import_generator.py`) records
    the .csv row order in `_ds_row` after `insheet` and restores it before
    saving. On a rerun, appending the saved .dta and `sort KEY` had left the
    rows in KEY order, so positional prep steps dropped different
    submissions. Saved rows take the position of the new row with the same
    KEY; rows found only in the saved .dta go last
  - `generate_prepare_data_script` and `build_replication_package` take an
    `on_warning` callback. A step that can't be translated gets a `NOTE` line
    in `prepare_data.do` and a warning on the Replication page, which keeps it
    beside the download button, instead of stopping the build. This covers
    emitters that raise and the cases they don't support (`uuid` columns,
    unsupported transform, add-column or remove-row methods and conditions,
    unknown actions), which now raise `_UntranslatableStepError` instead of
    returning a silent `NOTE`. A row-index step with no values stays a silent
    no-op
  - The row-index help text on the Prep page now describes this syntax.
    `TestStataRemoveRows` expected the 0-based output and is corrected
- **Enumerator Report: overview without named enumerators**: data where no
  submission names an enumerator (such as a team whose enumerator values are
  all blank) stopped the report at `compute_overview_figures`, before Needs
  attention. `OverviewFigures.median_per_enumerator`, `fewest` and `most` are
  now None then, and "Submissions per enumerator" shows a dash
- **Needs attention: enumerators in two teams**: with a team column and "All
  teams", the rules read the summary table's one row per enumerator and team,
  so an enumerator could get two "Missing answers" reasons, or a Consent or
  Completion reason from one team's work only. The rules now read
  `compute.compute_attention_summary` (replacing
  `compute_enumerator_missing_shares`), grouped by enumerator alone; the
  summary table still groups by team
- **Needs attention: GPS with numeric enumerator IDs**: an integer
  enumerator or team column with a blank came back from detection's
  `to_pandas` as floats, so `GPSOutlierSummary.unreviewed_by` named ID 101
  "101.0" and every GPS reason was dropped without an error. It now takes
  the survey data's schema and reads the names and teams back with their
  polars dtype before casting to text, so IDs stored as floats keep "101.0"
- **Needs attention: Response Patterns settings**: the list ran Response
  Patterns on the raw saved settings, so a variable since set as the team,
  survey ID or survey key column (which the section drops) could flag every
  enumerator. `settings_ui.effective_response_pattern_settings` applies the
  section's variable-editor filtering without rendering, and
  `report_ui._list_patterns` uses it with `excluded_columns` (was
  `_excluded_columns`), so both run on the same settings and cache entry
- **Needs attention: relative rule** (`attention.count_reasons`): an
  enumerator's rate was compared with the team's including their own
  issues, so one doing most of the interviews could hide (30 outliers in 90
  against a colleague's 1 in 10 gave no reason), and the rule did not need
  `MIN_SUBMISSIONS`. Rates now compare with the rest of the team's, need 5
  submissions, and any issues against none for the rest of the team are
  Flagged
- **Needs attention: submissions with no enumerator**:
  `attention.activity_reasons` and `form_version_reasons` dropped them
  before finding the latest submission and the newest version's release, so
  an unnamed newest submission hid inactivity and outdated forms. They now
  count for those dates and are left out only when attributing reasons

## [1.2.1] - 2026-11-06

### Fixed

- **SurveyCTO date and datetime questions imported blank** (#395): every form
  question of type `date`, `datetime` or `time` imported as an all-null
  `Datetime` column. The standard columns (`SubmissionDate`, `starttime`,
  `endtime`, `CompletionDate`) and local-file imports were not affected
  - Root cause: `DataProcessor._convert_column_by_type` parsed them with
    `format="%+"` (ISO 8601 with an offset) and `strict=False`. The wide JSON
    API sends `"Mar 7, 2025"` and `"Mar 7, 2025 4:06:12 PM"`, so every value
    turned null without a warning
  - Solution: `date` parses strictly with `"%b %d, %Y"` to `Date`, and
    `datetime` with `SurveyCTOConfig.date_format` to a naive `Datetime`. A
    value in any other format raises, and the existing `PolarsError` handler
    keeps the column as text and logs a warning. `time` stays text because its
    wide-JSON format is not confirmed. Skipped answers are already null after
    `standardize_missing_values`, so they don't fail the column. The next
    import fills the columns in. #397 replaces this parsing in 1.3.0

## [1.2.0] - 2026-11-03

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
- **Replication package**: An **Exclude reviewer names** checkbox on the Export
  Replication Package page blanks the `user` column in the exported
  `correction_log.csv`. The column is kept so the schema matches
  `CORRECTION_LOG_SCHEMA`, and the project's stored log is not changed. Off by
  default; changing it discards an already-built package
  (`build_replication_package(exclude_reviewer_names=...)`,
  `src/datasure/views/replication_view.py`) — closes #332
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
  - Later in 1.2.0 the cards became rows and the headlines return a
    `CheckHeadline`: see **Check health rows** and **Breaking: headline
    functions return `CheckHeadline`** under Changed, and **Breaking: check
    health cards** under Removed
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
    `DEMO_THROWAWAY_PAGE`. `OnboardingSteps.REPLICATION` starts with a project
    export from the demo row, since ticking the PII confirmation at the end
    completes the demo, then builds the package in page order (**Page Name**,
    **Exclude reviewer names** just below it, then **Selected page details**).
    It explains Update from configuration and Delete project without running
    them
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
  `DEMO_OUTLIER_CORRECTION`, `DEMO_GPS_ACCEPT`, `DEMO_ATTRIBUTION_NO_NOTE`,
  `DEMO_ATTRIBUTION_WITH_NOTE`, `DEMO_SHARED_LONGITUDE`), each tested
  against the real demo data in `TestReviewGuidanceValues`. Records are a
  `DemoRecord` (hhid, KEY); `DemoFlag` and `DemoMismatch` hold one, and
  `DemoFlag` also replaces `DemoCorrection` for `DEMO_LAND_CORRECTION`. The
  Outliers and GPS callouts share `demo_accept_steps` and
  `DEMO_SHOW_REVIEWED`, and name the Review button by `REVIEW_BUTTON_LABEL`.
  The backcheck callout (`_attribution_guidance`) names the column by
  `ERROR_SOURCE_LABEL` ("Error Source"), the header users see. The GPS
  outliers guidance moved into `_render_gps_outliers_checks`, so it also
  shows without a Mapbox token

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
- **Dependencies**: `polars>=2.0.0,<3` (was `>=1.30.0`), lock moved from
  1.43.2 to 2.0.0. The floor is the tested major, so an existing install can
  no longer keep polars 1.x (see Fixed); polars 3 is excluded until
  tested — #426
- **Dependencies**: Relaxed the exact `streamlit==1.61.0` pin to
  `streamlit>=1.65.0,<2` (lock: Streamlit 1.66.0, Starlette 1.8.0). Only
  Streamlit major releases now need a deliberate bump (`pyproject.toml`) — #330
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
  breaking only against 1.2.0a3, which added the headlines (1.1.0 has none).
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
- **Breaking: check health cards** (#399, #365): `health_cards`,
  `render_health_grid` and `HealthCard`, added in 1.2.0a3, are removed from
  `checks/health.py`. The card headlines described above are now the rows'
  details
  - Migration: use `health_rows(ctx, items, headlines)` for the rows and
    `render_health_rows(rows, on_select)` to draw them; `HealthRow` replaces
    `HealthCard`, with `headline` a `CheckHeadline` and `state` a `RowState`
- **Apply Consent and Outcome Settings** (#353): The Enumerator settings
  button and the project-wide `enumerator_data_with_consent_outcome` table
  are removed; the flags are computed when the report runs

### Fixed

- **Silent exit on polars 1.x**: On Windows, the app exited with no
  traceback while the Duplicates tab was in use. Windows Error Reporting
  logged an access violation (`0xc0000005`) in `_polars_runtime.pyd`
  (polars-runtime-32 1.43.2)
  - Root cause: `polars>=1.30.0,<3` let an install made over an existing
    tool environment keep polars 1.43.2, which the test suite never runs.
    `uv tool upgrade` did not replace it when Test PyPI was added with
    `--index`, because uv's first-index strategy then fails to resolve
    `pandas` and `polars`, which also exist on Test PyPI, and leaves the
    environment unchanged
  - Solution: the polars floor is now 2.0.0 (see Changed), so the resolver
    must replace polars 1.x — #426
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
  Analysis tabs instead of always 0. The tiles were then removed with
  Summary's Data Quality section (#378, see Removed);
  `overall_error_rate_percent` and the settings fix below remain
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
- **Demo Learn More shared a row with check settings** (#365): on Summary,
  Progress, Duplicates, Outliers, GPS, Enumerator and Backchecks, the "Learn
  More" expander sat beside the settings expander instead of above it. The
  settings function draws it, and `reset_filters_beside` runs that function in
  a horizontal row. `reset_filters_beside` now wraps the row in
  `onboarding_utils.demo_guidance_above`, which reserves an `st.empty()` slot
  above the row, and `demo_expander` draws there
- **Demo configuration file set up nothing** (#365): a configuration exported
  from the demo's **Export** button imported 0 datasets and created 0 pages,
  and the result still showed as a success
  - Root cause: the demo's import_log rows use source `"Demo Data"`, which
    `_import_dataset` did not handle. `ImportSourceEntry.source` was a plain
    string, so the bundle passed validation and the Import button was enabled
  - Solution: `_import_dataset` dispatches to one helper per source, and the
    new `_import_demo_dataset` rebuilds the dataset with
    `onboarding_utils.build_demo_datasets`, split out of `load_demo_data`.
    The packaged CSVs can't be imported as local files instead: they lack the
    generated date and backcheck fields the pages use.
    `ImportSourceEntry.source` is now `Literal["SurveyCTO", "local storage",
    "Demo Data"]`, so a bundle with any other source is rejected when read.
    `_render_config_apply_result` shows an error when nothing was set up
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
