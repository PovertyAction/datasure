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

**Last Updated**: September 2026
**Document Version**: 1.1.0
