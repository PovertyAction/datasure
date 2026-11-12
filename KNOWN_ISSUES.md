# Known Issues

This page lists problems in DataSure that we already know about, with workarounds where we have one. **Before you open a new issue, check this list and [search the issue tracker](https://github.com/PovertyAction/datasure/issues?q=is%3Aissue).** If your problem is listed here, add a 👍 to the linked issue instead of opening a new one.

This page is a short, readable summary. The linked GitHub issue is the full record and is always more up to date. For what changed in each release, see [RELEASENOTES.md](RELEASENOTES.md) (user-facing) and [CHANGELOG.md](CHANGELOG.md) (technical).

To check which version you have, run `datasure --version`. Versions with `a`, `b` or `rc` in them (for example `1.2.0a1`) are pre-releases for testers, published on [Test PyPI](https://test.pypi.org/project/datasure/).

**Status key:** 🔴 Open · 🟡 Planned (fix scheduled) · 🟢 Fixed

## Contents

- [Open issues](#open-issues)
- [Recently fixed](#recently-fixed)
- [Maintaining this file](#maintaining-this-file)

## Open issues

### KI-034: The replication package fails or removes the wrong rows for "remove rows by row index" steps

- **Status:** 🟡 Planned for 1.2.2. Fixed in the 1.2.2a1 pre-release
- **Affected versions:** 1.0.0 – 1.2.1
- **Symptom:** If a Prep step removes rows **by row index** with a range such as `0:30`, **Build Replication Package** fails with `ValueError: invalid literal for int() with base 10: '0:30'`. With single row numbers, the package builds, but `prepare_data.do` removes different rows from the ones DataSure removed. Negative row numbers such as `-5` remove nothing, or the wrong rows, on the Prep page.
- **Workaround:** Install the 1.2.2a1 pre-release from [Test PyPI](https://test.pypi.org/project/datasure/) and rebuild the package. On earlier versions, list row numbers one by one instead of as a range, use only row numbers of 0 or more, and check every `drop` line in `prepare_data.do` by hand before you use it.
- **Issue:** [#442](https://github.com/PovertyAction/datasure/issues/442)

### KI-033: Date and datetime questions from SurveyCTO import as blank

- **Status:** 🟡 Planned for 1.2.1
- **Affected versions:** 1.0.0 – 1.2.0
- **Symptom:** After you import a form from SurveyCTO, every `date` and `datetime` question in the form shows as blank. These columns can look like skipped questions on the **Missing Values** tab. Submission dates, start and end times, and data imported from a local file are not affected.
- **Workaround:** Update to 1.2.1 when it is released, then refresh the form's data. Until then, export the data from SurveyCTO as a CSV and import it as a local file.
- **Issue:** [#395](https://github.com/PovertyAction/datasure/issues/395)

### KI-019: Datasets or check pages with similar names overwrite each other

- **Status:** 🟡 Planned for 1.3.0
- **Affected versions:** 1.0.0 and later
- **Symptom:** Two dataset aliases such as `baseline-1` and `Baseline 1`, or two check pages such as `HH HFC` and `hh-hfc`, are both accepted, but they share storage. Importing or saving one silently replaces the other. Datasets whose alias contains `-`, `.` or brackets, or starts with a digit, may also be missing from the Import page's preview list. Some page names make the check page crash.
- **Workaround:** Use only letters, digits and underscores in aliases and page names, start them with a letter, and do not reuse a name that differs only in case or punctuation.
- **Issue:** [#350](https://github.com/PovertyAction/datasure/issues/350)

### KI-018: Legacy `.xls` Excel files fail to import

- **Status:** 🟡 Planned. From 1.2.0, DataSure rejects `.xls` files with a clear message; reading `.xls` files is planned for 1.3.0
- **Affected versions:** 1.0.0 – 1.2.0a1
- **Symptom:** A local `.xls` file is accepted on the Import page, then fails with an error from `openpyxl`.
- **Workaround:** Open the file in Excel and save it as `.xlsx`, or export it as CSV.
- **Issue:** [#349](https://github.com/PovertyAction/datasure/issues/349) · [Changelog](CHANGELOG.md#120---2026-11-03)

### KI-015: Every SurveyCTO refresh downloads the whole dataset again

- **Status:** 🟡 Planned for 1.3.0
- **Affected versions:** 1.0.0 and later
- **Symptom:** Refreshing a SurveyCTO form takes as long as the first import, because DataSure downloads every submission instead of only new ones. Your data is still complete and correct.
- **Workaround:** None needed. Expect slow refreshes on large or encrypted forms.
- **Issue:** [#340](https://github.com/PovertyAction/datasure/issues/340)

## Recently fixed

### KI-032: DataSure closes without an error while you review duplicates

- **Status:** 🟢 Fixed in 1.2.0
- **Affected versions:** 1.2.0 pre-releases (seen on 1.2.0rc1) on Windows, when installed over an earlier DataSure install
- **Symptom:** While you work on the **Duplicates** tab, the app stops and the terminal returns to the prompt with no error, even with `datasure --logging debug`. The browser tab stops responding.
- **Fix:** Upgrade to 1.2.0 or later.
- **Issue:** [#426](https://github.com/PovertyAction/datasure/issues/426) · [Changelog](CHANGELOG.md#120---2026-11-03)

### KI-031: New installs fail to import data with `Resource In Use Error` or `no attribute 'pl'`

- **Status:** 🟢 Fixed in 1.2.0
- **Affected versions:** 1.0.0 – 1.2.0a6, when installed on or after 2026-10-21
- **Symptom:** On a new install, importing data or opening a check page fails with `Resource In Use Error: connection has an unfinished result from execute()` or `'DuckDBPyConnection' object has no attribute 'pl'`. Installs made before 21 October 2026 are not affected unless you reinstall or upgrade.
- **Fix:** Upgrade to 1.2.0 or later.
- **Issue:** [#393](https://github.com/PovertyAction/datasure/issues/393) · [Changelog](CHANGELOG.md#120---2026-11-03)

### KI-030: Outliers & Constraints and GPS Checks tabs crash with `cannot compare string with numeric type (i32)` after applying a project setup

- **Status:** 🟢 Fixed in 1.2.0
- **Affected versions:** 1.2.0a2 – 1.2.0a5
- **Symptom:** After you apply an exported project setup that includes corrections, the **Outliers & Constraints** and **GPS Checks** tabs show `ComputeError: cannot compare string with numeric type (i32)`.
- **Fix:** Upgrade to 1.2.0 or later. Projects that already show the error load again after the update.
- **Issue:** [#352](https://github.com/PovertyAction/datasure/issues/352) · [Changelog](CHANGELOG.md#120---2026-11-03)

### KI-029: Missing codes such as -99 are counted as values in Outliers, Descriptive Stats and Enumerator Stats

- **Status:** 🟢 Fixed in 1.2.0
- **Affected versions:** 1.0.0 – 1.2.0a4
- **Symptom:** Codes you add on the Missing Values tab, such as `-99` for Don't know, are treated as real answers on other tabs. On **Outliers & Constraints**, `-99` answers are flagged as outliers or constraint violations, and they count towards the outlier % on the Summary tab. On **Descriptive Stats** and in **Column Statistics by Enumerator**, they pull down the mean and show as the minimum.
- **Fix:** Upgrade to 1.2.0 or later.
- **Issue:** [#379](https://github.com/PovertyAction/datasure/issues/379) · [Changelog](CHANGELOG.md#120---2026-11-03)

### KI-028: Enumerator summary shows wrong first and last submission dates and this week/month counts

- **Status:** 🟢 Fixed in 1.2.0
- **Affected versions:** 1.0.0 – 1.2.0a3
- **Symptom:** On the Enumerator tab, when your data covers more than one month, the summary table can show the wrong **first submission** and **last submission** dates, and **# submissions this week** and **# submissions this month** can include submissions from earlier months. For example, 30 Sep can be counted in October's "this month", and an enumerator who started in January can show April as their first submission.
- **Fix:** Upgrade to 1.2.0 or later.
- **Issue:** [#380](https://github.com/PovertyAction/datasure/issues/380) · [Changelog](CHANGELOG.md#120---2026-11-03)

### KI-027: Outliers & Constraints and GPS Checks tabs crash with `unable to find column "action"`

- **Status:** 🟢 Fixed in 1.2.0
- **Affected versions:** 1.2.0a1 only
- **Symptom:** In a project with no corrections yet, the **Outliers & Constraints** and **GPS Checks** tabs show `ColumnNotFoundError: unable to find column "action"`. This can start after you re-run prep or refresh the data. It can also start as soon as you open a project you used with 1.1.0, if you re-imported its data in that version.
- **Fix:** Upgrade to 1.2.0 or later.
- **Issue:** [#368](https://github.com/PovertyAction/datasure/issues/368) · [Changelog](CHANGELOG.md#120---2026-11-03)

### KI-026: Outliers tab crashes after you delete an outlier column

- **Status:** 🟢 Fixed in 1.2.0
- **Affected versions:** 1.0.0 – 1.2.0a1
- **Symptom:** After you use **Delete outlier column** on the Outliers tab, the tab shows an error every time it loads: `DuplicateError: column with name 'index' has more than one occurrence`.
- **Fix:** Upgrade to 1.2.0 or later. Pages that already show the error load again after the update.
- **Issue:** [#368](https://github.com/PovertyAction/datasure/issues/368) · [Changelog](CHANGELOG.md#120---2026-11-03)

### KI-025: The Summary tab's outlier % and back check error rate always show 0

- **Status:** 🟢 Fixed in 1.2.0
- **Affected versions:** 1.0.0 – 1.2.0a2
- **Symptom:** The Summary tab shows 0 for outlier % and back check error rate in every project, even when the Outliers and Backchecks tabs show flags. These tiles have not been built yet. A 0 here does not mean there are no problems.
- **Fix:** Upgrade to 1.2.0 or later. These tiles are replaced by the **Outliers & Constraints** and **Backchecks** rows in Summary's check health list.
- **Issue:** [#358](https://github.com/PovertyAction/datasure/issues/358) · [Changelog](CHANGELOG.md#120---2026-11-03)

### KI-024: Restart Demo keeps your earlier corrections and settings

- **Status:** 🟢 Fixed in 1.2.0
- **Affected versions:** 1.0.0 – 1.2.0a6
- **Symptom:** After **Restart Demo**, corrections and check settings from your last demo session come back when you recreate the "Household HFCs" check page, so the demo guidance no longer matches what you see. The Restart dialog says corrections are deleted, but they are not.
- **Fix:** Upgrade to 1.2.0 or later.
- **Issue:** [#357](https://github.com/PovertyAction/datasure/issues/357) · [Changelog](CHANGELOG.md#120---2026-11-03)

### KI-023: Demo guidance mentions labels and columns that do not exist

- **Status:** 🟢 Fixed in 1.2.0
- **Affected versions:** 1.0.0 – 1.2.0a6
- **Symptom:** Some demo steps ask you to pick a column or option that is not in the demo data or on the page. For example, they mention `household_size` (the column is `household_count`) and "Select column to group by" (the label is "Group by column").
- **Fix:** Upgrade to 1.2.0 or later.
- **Issue:** [#356](https://github.com/PovertyAction/datasure/issues/356) · [Changelog](CHANGELOG.md#120---2026-11-03)

### KI-022: Check pages share Descriptive Statistics columns and enumerator consent results

- **Status:** 🟢 Fixed in 1.2.0
- **Affected versions:** 1.0.0 – 1.2.0a4
- **Symptom:** Choosing Descriptive Statistics columns on one check page changes them on every other page in the project. The Enumerator report keeps showing old consent and outcome results after a data refresh, or after you change the settings on another page.
- **Fix:** Upgrade to 1.2.0 or later.
- **Issue:** [#353](https://github.com/PovertyAction/datasure/issues/353) · [Changelog](CHANGELOG.md#120---2026-11-03)

### KI-021: Exporting a project setup leaves out some check settings

- **Status:** 🟢 Fixed in 1.2.0
- **Affected versions:** 1.1.0 – 1.2.0a4
- **Symptom:** After you apply an exported project setup to another project, these settings are missing: missing-value codes, Descriptive Statistics columns, and the column rules for Duplicates, Outliers, GPS and Backchecks.
- **Fix:** Upgrade to 1.2.0 or later and export the setup again. Setups exported by an older version still leave these settings out.
- **Issue:** [#352](https://github.com/PovertyAction/datasure/issues/352) · [Changelog](CHANGELOG.md#120---2026-11-03)

### KI-020: "Remove rows" also removes rows with a missing value in the selected column

- **Status:** 🟢 Fixed in 1.2.0
- **Affected versions:** 1.0.0 – 1.2.0a6
- **Symptom:** A prep step such as "remove rows where `age` is greater than 60" also removes rows where `age` is blank. The step's affected-row count includes those rows. Replication scripts exported from DataSure do the same.
- **Fix:** Upgrade to 1.2.0 or later. Check the affected-row count of saved **Remove rows** steps on columns with blank values, since they now keep more rows.
- **Issue:** [#351](https://github.com/PovertyAction/datasure/issues/351) · [Changelog](CHANGELOG.md#120---2026-11-03)

### KI-017: Remove Credentials reports success but keeps the saved password

- **Status:** 🟢 Fixed in 1.2.0
- **Affected versions:** 1.0.0 – 1.2.0a1
- **Symptom:** On the Import page, **Remove Credentials** shows a success message, but the SurveyCTO password or private key is still saved on your computer and usually still appears in the list.
- **Fix:** Upgrade to 1.2.0 or later.
- **Issue:** [#342](https://github.com/PovertyAction/datasure/issues/342) · [Changelog](CHANGELOG.md#120---2026-11-03)

### KI-016: SurveyCTO imports leave out submissions completed before 2024

- **Status:** 🟢 Fixed in 1.2.0
- **Affected versions:** 1.0.0 – 1.2.0a1
- **Symptom:** A SurveyCTO form imports without error, but submissions completed before 1 January 2024 are missing. The row count is lower than in the SurveyCTO console.
- **Fix:** Upgrade to 1.2.0 or later; the next refresh downloads the older submissions.
- **Issue:** [#341](https://github.com/PovertyAction/datasure/issues/341) · [Changelog](CHANGELOG.md#120---2026-11-03)

### KI-014: A correction overwrites a value the field team fixed, if the cell was blank

- **Status:** 🟢 Fixed in 1.2.0
- **Affected versions:** 1.1.0 – 1.2.0a1
- **Symptom:** You fill a blank cell with a correction. Later the field team fills the same cell at source and you re-import. DataSure replaces their value with your correction and gives no warning. A correction to a cell that was not blank correctly warns instead.
- **Fix:** Upgrade to 1.2.0 or later. Such a correction now fails with a reason and the field team's value is kept.
- **Issue:** [#337](https://github.com/PovertyAction/datasure/issues/337) · [Changelog](CHANGELOG.md#120---2026-11-03)

### KI-013: The app loads, then disconnects without a message

- **Status:** 🟢 Fixed in 1.2.0
- **Affected versions:** 1.1.0 – 1.2.0a1, when installed on or after 2026-10-13
- **Symptom:** DataSure opens in the browser, then loses its connection. The terminal shows `RuntimeError: Expected ASGI message 'http.response.start', but got 'http.response.body'`.
- **Fix:** Upgrade to 1.2.0 or later.
- **Issue:** [#330](https://github.com/PovertyAction/datasure/issues/330) · [Changelog](CHANGELOG.md#120---2026-11-03)

### KI-012: Fresh installs crash on the Prep page and several check pages

- **Status:** 🟢 Fixed in 1.2.0
- **Affected versions:** 1.0.0 – 1.2.0a1, when installed after polars 2.0 was released
- **Symptom:** The Prep page and several checks (Duplicates, Missing, Summary, Outliers, Enumerator) stop with an error such as `AttributeError: module 'polars' has no attribute 'NUMERIC_DTYPES'`.
- **Fix:** Upgrade to 1.2.0 or later.
- **Fix PR:** [#329](https://github.com/PovertyAction/datasure/pull/329) · [Changelog](CHANGELOG.md#120---2026-11-03)

### KI-011: A prep step that removes every row brings back the raw data

- **Status:** 🟢 Fixed in 1.2.0
- **Affected versions:** 1.0.0 – 1.2.0a1
- **Symptom:** If a "remove rows" step removes every row, check pages show the original raw data instead of an empty dataset. The Prep page then says "No data available to prepare" and hides the controls you would use to remove that step.
- **Fix:** Upgrade to 1.2.0 or later.
- **Issue:** [#315](https://github.com/PovertyAction/datasure/issues/315) · [Changelog](CHANGELOG.md#120---2026-11-03)

### KI-010: Duplicates "Records to Include" filters leak between pages or disappear

- **Status:** 🟢 Fixed in 1.2.0
- **Affected versions:** 1.0.0 – 1.1.0
- **Symptom:** In a project with more than one check page, setting the Records to Include filter on one page changes another page's results. A filter that matches no records checks every record instead. Some saved filters come back empty in a new session.
- **Fix:** Upgrade to 1.2.0 or later.
- **Issue:** [#306](https://github.com/PovertyAction/datasure/issues/306) · [Changelog](CHANGELOG.md#120---2026-11-03)

### KI-009: The Mapbox token entered in GPS settings is not saved

- **Status:** 🟢 Fixed in 1.2.0
- **Affected versions:** 1.0.0 – 1.1.0
- **Symptom:** You enter a Mapbox token in the GPS settings, but the map does not use it, and it is gone in your next session.
- **Fix:** Upgrade to 1.2.0 or later.
- **Issue:** [#304](https://github.com/PovertyAction/datasure/issues/304) · [Changelog](CHANGELOG.md#120---2026-11-03)

### KI-008: Back check dates and "Avg Days" are empty

- **Status:** 🟢 Fixed in 1.2.0
- **Affected versions:** 1.0.0 – 1.1.0
- **Symptom:** On the Backchecks tab, back check dates and "Avg Days" statistics are blank when survey and back check submissions have different KEYs. Backchecker statistics are also blank when the survey KEY is used as the ID.
- **Fix:** Upgrade to 1.2.0 or later.
- **Issue:** [#300](https://github.com/PovertyAction/datasure/issues/300) · [Changelog](CHANGELOG.md#120---2026-11-03)

### KI-007: Back check Duplicate Handling and target % settings have no effect

- **Status:** 🟢 Fixed in 1.2.0
- **Affected versions:** 1.0.0 – 1.1.0
- **Symptom:** On the Backchecks tab, duplicates are always dropped and the back check target is always 10%, whatever you choose.
- **Fix:** Upgrade to 1.2.0 or later. The Duplicate Handling setting is removed and duplicates are left out until you resolve them (see [RELEASENOTES.md](RELEASENOTES.md)). Targets saved in earlier versions are not carried over, so set the target again after upgrading.
- **Issue:** [#299](https://github.com/PovertyAction/datasure/issues/299) · [Changelog](CHANGELOG.md#120---2026-11-03)

### KI-006: `datasure` did not open the browser

- **Status:** 🟢 Fixed in 1.1.0
- **Affected versions:** 1.0.0
- **Symptom:** Running `datasure` started the app but did not open a browser tab.
- **Fix:** Upgrade to 1.1.0 or later. On 1.0.0, open the address shown in the terminal.
- **Fix PR:** [#284](https://github.com/PovertyAction/datasure/pull/284) · [Changelog](CHANGELOG.md#110---2026-09-21)

### KI-005: "Remove rows" with a range condition crashed on blank values

- **Status:** 🟢 Fixed in 1.1.0
- **Affected versions:** 1.0.0
- **Symptom:** Adding a range condition on a numeric column with blank values crashed with `TypeError: '<' not supported between instances of 'float' and 'NoneType'`.
- **Fix:** Upgrade to 1.1.0 or later.
- **Issue:** [#281](https://github.com/PovertyAction/datasure/issues/281)

### KI-004: Dates and times without seconds crashed data preparation

- **Status:** 🟢 Fixed in 1.1.0
- **Affected versions:** 1.0.0
- **Symptom:** Converting text such as `3/15/2026 17:28` to a date and time on the Prep page crashed the app.
- **Fix:** Upgrade to 1.1.0 or later.
- **Issue:** [#261](https://github.com/PovertyAction/datasure/issues/261) · [Changelog](CHANGELOG.md#110---2026-09-21)

### KI-003: One failing step stopped "reapply all" on the Prep page

- **Status:** 🟢 Fixed in 1.1.0
- **Affected versions:** 1.0.0
- **Symptom:** If one prep step failed, for example because a re-import removed a column it used, the Prep page crashed. Failing corrections were skipped without a message.
- **Fix:** Upgrade to 1.1.0 or later. The failing step or correction is now skipped and reported, and the rest still run.
- **Issue:** [#253](https://github.com/PovertyAction/datasure/issues/253) · [Changelog](CHANGELOG.md#110---2026-09-21)

### KI-002: Re-importing data left old results on the Prep and Correct Data pages

- **Status:** 🟢 Fixed in 1.1.0
- **Affected versions:** 1.0.0
- **Symptom:** After you re-imported raw data, the Prep and Correct Data pages and the reports still showed data from the previous import.
- **Fix:** Upgrade to 1.1.0 or later.
- **Issue:** [#252](https://github.com/PovertyAction/datasure/issues/252) · [Changelog](CHANGELOG.md#110---2026-09-21)

### KI-001: "Remove rows" with *equal to* or *not equal to* did the opposite

- **Status:** 🟢 Fixed in 1.1.0
- **Affected versions:** 1.0.0
- **Symptom:** Rows that matched the condition were kept and the other rows were removed. Exported Stata replication scripts had the same problem.
- **Fix:** Upgrade to 1.1.0 or later. Check prep steps that use these conditions.
- **Issue:** [#246](https://github.com/PovertyAction/datasure/issues/246) · [Changelog](CHANGELOG.md#110---2026-09-21)

## Maintaining this file

This file is a curated summary for users. [GitHub Issues](https://github.com/PovertyAction/datasure/issues) remains the source of truth.

- **Add** a user-visible bug when it is confirmed, or when it affects a released version and is likely to be reported more than once. Give it the next unused ID, so newer entries have higher numbers, and list entries newest first in each section. **Never reuse or renumber IDs**, even after an entry is removed.
- **Write for users.** Describe what users see, using the labels on screen, and quote the error text so people can search for it. Do not explain the cause or copy details from CHANGELOG.md or the issue; link to them instead.
- **Set the status from the milestone.** 🟡 Planned means the issue is in a release milestone, or its fix is merged or only in a pre-release (Test PyPI). Otherwise use 🔴 Open. Use 🟢 Fixed only once the fix is in a stable release on PyPI.
- **When a fix ships in a stable release,** move the entry to "Recently fixed", set 🟢 with the release version, replace the workaround with the fix, and link the version's changelog section.
- **Keep fixed entries for 2–3 releases,** then remove them. CHANGELOG.md keeps the full history.
- **Close the loop with the release:** review this file as part of the release checklist.
