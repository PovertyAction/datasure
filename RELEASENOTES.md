# DataSure Release Notes

**DataSure** is IPA's Data Management System Dashboard - a comprehensive tool for survey data quality monitoring and high-frequency checks (HFCs) in research projects.

This document tracks user-facing changes and improvements to help data managers, survey coordinators, and research teams understand new features and enhancements in each release.

---

## About This Document

**Purpose**: Communicate new features, improvements, and bug fixes to end users in accessible, non-technical language.

**Audience**: Data managers, survey coordinators, research teams, and field staff using DataSure for survey data quality assurance.

**Related Documentation**:

- **[CHANGELOG.md](CHANGELOG.md)**: Technical implementation details for developers

---

## Version 1.2.0 — Review and Correct Where You Find the Problem

Released: October 2026

This release lets you deal with a problem on the check page that found it. You can correct or accept flagged outliers, constraint violations and GPS points, resolve duplicate IDs on side-by-side cards, and attribute back check mismatches to whoever caused them. Every decision goes into one correction log that records who made it and where. Summary now shows each check's outstanding and resolved issues and how they changed since yesterday. Back checks gain coverage targets and adjusted error rates. Check pages are quicker to move around and remember your filters.

### New Features

#### Correct or accept flagged values from the Outliers & Constraints tab

Each row of the constraint violations and outlier tables has a **Review** button. It opens a form with the record and value filled in, where you can change the value, blank it, or **accept** it as correct with a reason. Accepted flags are hidden and no longer counted. Turn on **Show reviewed** to see them, and the values you corrected, highlighted in green with the reason. **Show only flagged values** (on by default) and **Show only reviewed** narrow the tables further. Accepting a value past a hard limit asks you to confirm first. An acceptance lapses, and the value is flagged again, if the value changes.

#### Correct or accept GPS outliers

Each GPS outlier also has a **Review** button. You can enter new coordinates, clear the coordinates, remove the record, or accept the location as correct. Accepted points are drawn in green on the map and left out of the outlier count. The Mapbox token you enter in the GPS settings is now saved securely on your computer and shared by all your projects.

#### Compare and resolve duplicate IDs on cards

The Duplicates tab shows one card per duplicate ID, with the records side by side and the fields that differ highlighted. **Compare all fields** and **Only differing fields** control what each card shows. You can search by ID or KEY, sort the cards, and download every duplicate record as a CSV. Pages with back check data have a **Survey data** / **Backcheck data** switcher, and the back check view also lists back checks whose ID is not in the survey data.

On each card, choose **Keep**, **Modify ID** or **Drop** for every record, give one reason and note, and save the whole card in one step. Save stays disabled, with a message saying what's missing, until at most one record keeps the ID and every new ID is valid, so a card can't be half fixed. Unmatched back check cards let you fix the mistyped ID or drop the back check. Every change is logged on the Correct Data page, where you can undo it. The **Resolved** metric counts the duplicate IDs your corrections have resolved.

#### Attribute back check mismatches and see adjusted error rates

Back check results measure how well data was collected, so mismatches are never corrected or accepted. Instead, click **Review** on a mismatch in the comparison details and say who caused it: the **Enumerator**, the **Backchecker** or the **Respondent**. A note is required for the last two. Select several rows to attribute them together. The **Attribution log** lists every attribution with who made it and when.

The enumerator and back checker statistics now show an **adjusted error rate** next to the regular one. It leaves out the mismatches attributed to someone else, so each person is measured on their own mistakes. The regular error rate never changes. Set an **Error rate target (%)** to highlight every rate above it. The Backchecks summary shows **Mismatches Attributed** and an **Error Rates** section with the total and per-category rates.

#### Track back check coverage against your target

A new **Targets** section shows **Backcheck Coverage** (the share of eligible surveys that have a back check, against your target %) and, when the page has a survey target, **Backchecks vs Expected**. An optional **Eligibility Filter** limits coverage to the surveys that can be back checked, for example consented ones. The enumerator statistics show each enumerator's coverage, including enumerators with no back checks yet.

#### One correction log for every page, with who made each entry

The Correction Log now records which page made each entry and who made it. Set your **Reviewer name** in the sidebar once; until you do, DataSure uses your computer login. **Source** and **Action** filters above the log show, for example, only GPS acceptances. When you build a replication package to share outside your team, tick **Exclude reviewer names** to leave the names out of the exported log.

#### Correct back check data on the Correct Data page

Pages with back check data have a **Survey data** / **Backcheck data** switcher on the Correct Data page. Back check data can only have its ID fixed or a record removed, since back check results measure data quality. Back check data you never prepared can now be corrected too.

#### Faster check pages that remember where you were

Check pages now show the checks in four groups (**Overview**, **Data integrity**, **Field team** and **Exploration**), with buttons for the checks in each group. Only the check you select runs, so pages open faster. The page address names the check, so you can bookmark or share a link to it, and the page reopens on the check you last viewed.

Each check remembers its filters, selections and sort order when you switch checks and when you reopen the app. **Reset filters** beside each check's settings clears that check's choices only. Remembered filters are personal: they are not included in exported setups or replication packages.

A check that can't show results yet is marked **not set up** or **not applicable** with the reason, and a check that fails shows its error without breaking the rest of the page. The Prepare Data and Correct Data pages use the same buttons in place of tabs, and Prepare Data has a **Columns to show** filter for its preview.

#### See every check's status on the Summary tab

Summary's Data Quality section is replaced by a check health list with one row per check, grouped like the check page. Each row shows a status (**No issues**, **Flagged**, **Ready**, **Not set up**, **Not applicable** or **Error**), the issues still **Outstanding**, and the issues already **Resolved** through corrections, acceptances or attributions. **Open →** or **Set up →** takes you to the check. Each number matches what the check itself shows, using that check's settings and corrections. If one check's saved settings no longer fit the data, its row shows the error and the other rows still load.

A **Change** column shows what changed over a period, for example "+3 since yesterday". Pick the period in the **Comparison period** box: Day (the default), 7 days, Week (week to date, with a week start you choose), 30 days or Month. The choice is saved for the project. Changes need a date column; if Summary has none, a note tells you to set one in Summary settings.

GPS Checks counts its outliers here too, using the settings you last chose on the GPS Checks tab. Without a Mapbox token, the GPS Checks tab still lists the outliers; only the map is hidden.

#### Exported project setups include every check setting

An exported project setup now carries your missing-value codes, Descriptive Statistics columns, and the column rules for Duplicates, Outliers, GPS and Backchecks. Before, these had to be set again after applying the setup. When you apply a setup to an existing project, its missing-value codes are added to the project's, and the setup's code wins where both use the same label. Applying a setup exported by an older version shows a note that these settings are not in it.

**Export configuration** in a project's **More** menu now opens a dialog with one option, **Include record-level decisions (corrections and backcheck attribution)**. Untick it to share a setup without decisions about individual records, for example when reusing it for a new survey round.

#### Join columns and convert columns to text or numbers on the Prep page

- **Join text columns**: **Add Column** has a **concat** method that joins two or more text columns in the order you pick them, with a space, comma, underscore, hyphen, no separator or your own text between them. Blank values are skipped
- **To text**: **Transform Column** can turn number, date, date-time and true/false columns into text
- **To number**: **Transform Column** can turn true/false columns into 1 and 0

The Stata replication script does the same steps.

#### A demo that covers the whole workflow

The demo now walks you through reviewing flagged values: accepting and correcting outliers, accepting a GPS outlier, and attributing back check mismatches. It also covers setting your reviewer name, editing and removing check pages, the SurveyCTO import forms (without needing a server or credentials), and exporting the demo project's setup with the new **Export** button on the Start page's demo row. The demo data is the same every time you start it, with the latest submissions dated today, and every check the demo visits has something to show. **Restart** now asks for confirmation and starts the demo from scratch, and the demo ends once, after the replication package step, with options to restart or create a real project.

### Changes

#### Back check comparison follows Records to Include and leaves out duplicates

The back check comparison and coverage now use the same records as the Duplicates tab: the **Records to Include** filters apply, and the page says how many surveys and back checks are compared. The **Duplicate Handling** setting is gone. Records whose ID is duplicated are always left out of the comparison until you resolve the duplicate, and a warning above Comparison Results Details counts them. If a page was set to keep the first or last duplicate, it now leaves duplicates out.

#### Records to Include applies straight away, on each page

The Duplicates **Records to Include** filter now applies as soon as you set it, without an **Apply Filter** button. Each check page keeps its own filter, and a filter that matches no records shows a warning instead of quietly checking every record.

#### Each check page keeps its own Descriptive Statistics columns and consent results

Choosing Descriptive Statistics columns on one check page no longer changes them on other pages. The first time you open a page after upgrading, it starts from your previous selection.

The Enumerator report now uses the page's saved consent and outcome settings every time it runs, so it stays current after a data refresh or a settings change. The **Apply Consent and Outcome Settings** button is gone. If consent or outcome is not set up, the **% consent** and **% completed survey** columns are hidden instead of showing 100%, and the consent and outcome columns start empty until you choose them.

#### Missing Values on Summary

Summary's Missing Values row reports the share of columns that are entirely missing. Summary no longer has its own **Survey ID** setting, which only fed the old duplicates chart; the Duplicates row uses the Duplicates tab's settings.

#### Legacy Excel files

DataSure now rejects `.xls` files when you add them, with a message to save the file as `.xlsx`. Before, they were accepted and then failed to import.

### Before You Upgrade

Your projects open in 1.2.0 without any steps, but a few results can change:

- **Back check target**: targets saved in earlier versions were never applied, and they are not carried over. Set the target again on the Backchecks tab, or leave it to the page configuration.
- **Back check duplicates**: records with a duplicated ID are now left out of the comparison until you resolve them, so the number of compared records can drop.
- **Remove rows steps**: saved steps on columns with blank values may now keep more rows (see Bug Fixes).
- **Missing-value codes**: codes such as `-99` are no longer counted as values on Outliers & Constraints, Descriptive Statistics and Enumerator Statistics, so their counts and averages can change.

### Bug Fixes

- **Fixed**: New installs crashed on the Prep page and several check pages with `module 'polars' has no attribute 'NUMERIC_DTYPES'`
- **Fixed**: New installs could not import data, failing with `Resource In Use Error` or `'DuckDBPyConnection' object has no attribute 'pl'`
- **Fixed**: The app loaded in the browser and then disconnected, with `Expected ASGI message 'http.response.start'` in the terminal
- **Fixed**: SurveyCTO imports left out submissions completed before 1 January 2024. The next refresh after you upgrade downloads them
- **Fixed**: **Remove Credentials** said it had removed a SurveyCTO password but left it saved on your computer
- **Fixed**: A correction that filled a blank cell overwrote the value the field team later entered at source. The field team's value is now kept and the correction shows why it no longer applies
- **Fixed**: Corrections saved with a value such as `25.0` against a whole number `25` were undone on the next refresh, and **Apply** stayed disabled for a new value of `0`
- **Fixed**: A prep step or correction that removed every row brought back the raw data on check pages. Check pages now say the dataset has no rows, and the Prepare Data and Correct Data pages keep the controls you need to undo the step
- **Fixed**: A **Remove rows** step with a condition also removed rows where the selected column was blank. Rows are now removed only when the condition is true, and the step says how many rows were kept because of a blank value. With several columns selected, every condition now removes a row when any column matches. Check the row counts of saved steps on columns with blank values, since they may now keep more rows. Exported Stata scripts match
- **Fixed**: Missing-value codes such as `-99` were counted as real answers in Outliers & Constraints, Descriptive Statistics and Enumerator Statistics, so they were flagged as outliers and pulled down means and minimums
- **Fixed**: Constraint violations past a hard limit were reported as soft violations when a soft limit was also set, so hard violations were undercounted
- **Fixed**: The Outliers tab failed on every load after you deleted an outlier column. Affected pages load again after you update
- **Fixed**: Duplicates **Records to Include** filters on one check page changed another page's results, and some saved filters came back empty in a new session
- **Fixed**: The back check target % and **Duplicate Handling** settings had no effect
- **Fixed**: Back check dates and **Avg Days** were blank when survey and back check records had different KEYs, and back checker statistics were blank when the survey KEY was used as the ID
- **Fixed**: The Mapbox token entered in the GPS settings was not saved
- **Fixed**: The Enumerator summary showed wrong first and last submission dates and this week/month counts when data spanned more than one month
- **Fixed**: The Summary tab's outlier % and back check error rate always showed 0. They are replaced by the Outliers & Constraints and Backchecks rows in the check health list
- **Fixed**: Check settings you had just saved could show their old values for up to a minute when you opened the check again
- **Fixed**: **Restart Demo** brought back corrections and settings from your last demo, and **Exit Demo** left demo data behind for your next project
- **Fixed**: The demo said it was complete several times before the last step, and its guidance named columns, labels and counts that did not match the demo data or the page
- **Fixed**: The Start page listed SPSS as a supported file type. It is not; the supported local formats are CSV, Excel (`.xlsx`), Stata, JSON and Parquet

For problems still open in this release and their workarounds, see [KNOWN_ISSUES.md](KNOWN_ISSUES.md).

---

## Version 1.1.0 — Reusable Project Setups

Released: September 2026

This release makes a project's setup portable: the way you configured one survey can be saved to a file and handed to a colleague, or reused for the next round. It also redesigns the project picker, clarifies preparation messages, and fixes several issues in data preparation and corrections.

### New Features

#### Share a project setup with a colleague

Export everything that defines how a project is set up — its import sources, preparation steps, quality check configuration, and corrections — into a single file, then apply it to a new or existing project. Instead of configuring a survey from scratch, a teammate can start from a setup that already works, and a follow-up round can reuse the previous round's configuration.

The exported file never contains survey data, passwords, or file paths specific to your computer, so it is safe to share by email or store alongside project documentation. Applying it replays the same steps you would perform by hand; anything that cannot apply to the new project is skipped and reported, so one mismatched step does not stop the rest of the setup from being restored.

#### Import Parquet files

Local file import now accepts Parquet files, alongside CSV, Excel, JSON, and Stata.

#### Survey ID shown with corrections

The Correct Data page and the Correction Log now show the survey ID for each correction, next to its status and status reason, so you can tell at a glance which submission a correction belongs to.

### Improvements

#### Redesigned project picker

The Start page previously offered a single dropdown that mixed real projects, the demo project, and "Create New Project" as if they were the same kind of choice. It is now a searchable, sortable list with one row per project: an **Open** button where you expect it, and a **More** menu holding the less frequent export, update, and delete actions. Creating a project has its own **+ New Project** dialog.

#### New projects open immediately

After you create a project, DataSure now loads and selects it for you instead of returning you to the project list to pick it manually.

#### Clearer data preparation messages

Confirmation messages after preparation steps now consistently tell you how many rows and columns the dataset has afterwards. Row-removal messages also state the actual column, condition, and value used, rather than only naming the method.

#### Consistent page layout

Page headings, section titles, metric rows, and confirmation dialogs now come from a shared set of building blocks, so every page in DataSure looks and behaves the same way. Filter settings wording on the duplicates check page has also been clarified.

### Bug Fixes

- **Fixed**: The "remove rows" preparation step with an *equal to* or *not equal to* condition did the opposite of what was asked — matching rows were removed instead of kept, and vice versa
- **Fixed**: Re-importing raw data now clears stale prepared and corrected data, so reports no longer show results from the previous import
- **Fixed**: Reapplying all preparation steps no longer crashes the page when one step fails (for example, when a re-import drops a column an earlier step used); the failing step is skipped and reported, and the rest still run. Reapplying all corrections now reports failures instead of passing over them silently
- **Fixed**: Dates and times without seconds are now parsed correctly during data preparation
- **Fixed**: Launching DataSure with `datasure` now opens your browser automatically, matching the behavior of the development command

---

## Version 1.0.0 — Initial Release

Released: July 2026

DataSure 1.0.0 is the first stable release of IPA's survey data quality monitoring tool. It brings together data import, preparation, nine configurable quality checks, and a replication package export in a single web-based dashboard.

### New Features

#### Connect to SurveyCTO or import local files

Download survey data directly from your SurveyCTO server with saved credentials. Passwords are stored in your operating system's secure keyring (Windows Credential Manager, macOS Keychain) — never written to disk or log files. Incremental refresh means only new submissions are downloaded each time.

Supports encrypted SurveyCTO forms with private key authentication, and imports local files in CSV, Excel (XLSX/XLS), JSON, and Stata (DTA) formats.

#### Automatic attachment download

Media files attached to survey responses (images, audio, video) can be downloaded and organized automatically, including attachments from encrypted forms.

#### Data preparation

Rename columns, filter rows, drop fields, and fix data types before running checks. All preparation steps are logged so your workflow is reproducible.

#### Nine built-in data quality checks

- **Summary**: Overall data quality score and flagged issues across all checks at a glance
- **Missing data**: Identify which fields have high rates of missing responses, broken down by enumerator or over time
- **Duplicates**: Detect duplicate survey submissions
- **GPS validation**: Map survey coordinates and flag outliers far from expected survey areas
- **Outliers**: Statistical detection of unusual values in numeric fields
- **Enumerator performance**: Track submission rates, duration, and quality by interviewer
- **Survey progress**: Daily and weekly submission counts against targets
- **Descriptive statistics**: Frequency tables and summary statistics for any field
- **Back-checks**: Compare original interviews against verification back-checks

#### Interactive report pages

Each check produces a report page with charts, maps, and tables that update automatically when new data is imported. Configure which checks run and which fields to include per project.

#### Data corrections

Log and apply corrections to individual survey responses within the app. Corrections are tracked separately from raw data — the original is always preserved.

#### Replication package export

A replication package is a set of scripts that re-runs your complete data pipeline — imports, preparation steps, and checks — independently of DataSure. Export one as Stata or Python to share your workflow with external researchers, submit alongside a publication, or archive a project at close-out.

#### Multi-project support

Manage multiple surveys simultaneously. Each project has its own settings, data, and check configuration stored locally.

### Bug Fixes

- **Fixed**: Encrypted attachment downloads now work correctly when a private key is configured
- **Fixed**: The application link shown after launch now reflects the correct address when a custom port is configured

---

## Getting Started

Install DataSure with uv (recommended):

```bash
uv tool install datasure
```

To upgrade an existing installation:

```bash
uv tool upgrade datasure
```

Then launch with `datasure`. For full installation instructions and system requirements, see [README.md](README.md).

---

## Support and Resources

### Getting Help

- **Documentation**: [DataSure How-To Guide](https://data.poverty-action.org/data-quality/datasure/how-to-datasure.html) — detailed instructions and training materials
- **GitHub Issues**: [Report bugs and request features](https://github.com/PovertyAction/datasure/issues)
- **Email Support**: <researchsupport@poverty-action.org>

### Contributing

DataSure is developed by Innovations for Poverty Action (IPA) with contributions from the research community. See CONTRIBUTING.md for development guidelines.

### License

DataSure is released under the MIT License. See LICENSE file for details.

---

## Version History

DataSure 1.0.0 is the first stable public release. Prior versions were internal pre-releases and are not documented here.

---

*This document is maintained alongside the project and updated with each release. For technical details, see [CHANGELOG.md](CHANGELOG.md).*

**Last Updated**: October 2026
**Document Version**: 1.2.0
