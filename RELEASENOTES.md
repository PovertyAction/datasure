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

Export a self-contained Stata or Python script package that reproduces your entire data pipeline outside DataSure. Useful for sharing with external researchers or archiving for publication.

#### Multi-project support

Manage multiple surveys simultaneously. Each project has its own settings, data, and check configuration stored locally.

### Bug Fixes

- **Fixed**: Encrypted attachment downloads now work correctly when a private key is configured
- **Fixed**: Browser URL now shows the correct port when launching with `--port`

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

**Last Updated**: July 2026
**Document Version**: 1.0.0
