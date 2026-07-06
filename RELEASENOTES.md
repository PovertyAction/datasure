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

## Getting Started with DataSure

### Installation Options

#### Install with pip

```bash
pip install datasure
```

#### Install with uv

Ensure that you have uv installed:

##### with winget

```bash
winget install astral-sh.uv
```

##### with homebrew

```bash
brew install uv
```

##### verify uv installation

```bash
uv --version
```

##### Install DataSure

```bash
uv tool install datasure
```

or update an existing installation:

```bash
uv tool upgrade datasure
```

### Quick Start

1. Launch the application: `datasure` (opens at <http://localhost:8501>)
   - Use a custom port: `datasure --port 8080`
2. Create your first project
3. Import survey data from SurveyCTO or upload CSV/Excel files
4. Configure data quality checks based on your survey requirements
5. Monitor data quality with interactive dashboards and reports

---

## Core Features

DataSure provides comprehensive survey data quality monitoring through:

### Data Quality Checks

- **Summary Statistics**: Overall project progress and completion tracking
- **Missing Data Analysis**: Identify patterns in incomplete responses
- **Duplicate Detection**: Find and manage duplicate survey entries
- **GPS Validation**: Verify location data accuracy with interactive maps
- **Outlier Detection**: Identify unusual responses requiring review
- **Enumerator Performance**: Monitor data collection team productivity
- **Progress Tracking**: Real-time survey completion monitoring
- **Descriptive Statistics**: Data distribution analysis and summaries
- **Back-check Management**: Verification workflow support

### Data Import and Management

- **SurveyCTO Integration**: Direct connection to your SurveyCTO server
- **Local File Support**: Import CSV, Excel (XLSX/XLS), JSON, and Stata (DTA) files
- **Multi-Project Organization**: Manage multiple surveys simultaneously
- **Flexible Configuration**: Customize checks per project requirements

### Reporting and Visualization

- **Interactive Dashboards**: Real-time data quality monitoring
- **Replication Package Export**: Generate Stata or Python scripts that reproduce your pipeline
- **Custom Charts**: Visualize data patterns and quality metrics

---

## System Requirements

- **Python**: Version 3.11 or higher
- **Operating System**: Windows, macOS, or Linux
- **Memory**: Minimum 4GB RAM (8GB recommended for large datasets)
- **Storage**: 1GB free space for application and data cache
- **Internet**: Required for SurveyCTO integration and updates

---

## Support and Resources

### Getting Help

- **GitHub Issues**: [Report bugs and request features](https://github.com/PovertyAction/datasure/issues)
- **Email Support**: <researchsupport@poverty-action.org>
- **Documentation**: See project documentation for detailed guides

### Contributing

DataSure is developed by Innovations for Poverty Action (IPA) with contributions from the research community. See CONTRIBUTING.md for development guidelines.

### License

DataSure is released under the MIT License. See LICENSE file for details.

---

## Version History

DataSure 1.0.0 is the first stable public release. Prior versions were internal pre-releases and are not documented here.

---

*This document is maintained alongside the project and updated with each release. For technical details, see CHANGELOG.md.*

**Last Updated**: July 2025
**Document Version**: 1.1
